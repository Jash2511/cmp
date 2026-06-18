import os
import json
from typing import Dict, Any , List
from groq import Groq
from pydantic import BaseModel , Field
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GROQ_API_KEY")

# ==========================================
# 1. PYDANTIC SCHEMA DEFINITION (ZOD EQUIVALENT)
# ==========================================
class ModerationResult(BaseModel):
    """
    Defines the strict structure and type constraints for the LLM output.
    Pydantic automatically validates these fields upon instantiation.
    """
    reasoning: str = Field(
        description="Brief explanation citing the specific rule, priority level, and conditions matched."
    )
    post_category: str = Field(
        description="The assigned single category. Must be one of: 'safe', 'self-harm', 'hate-speech', 'adult-content'."
    )
    confidence_score: float = Field(
        description="A floating-point confidence score between 0.0 and 1.0."
    )
    flagged_keywords: List[str] = Field(
        default_factory=list,
        description="An array of specific words or short phrases that triggered the category. Must be empty if category is 'safe'."
    )

# ==========================================
# 2. OPTIMIZED PROMPT GENERATOR
# ==========================================
def build_moderation_prompt(post_text: str, platform: str, age: str) -> str:
    system_prompt = """Analyze the User Post contextually based on the target platform and age metrics.

    [CLASSIFICATION TAXONOMY — PRIORITY ORDER]
    Assign exactly ONE category. Evaluate rules top-to-bottom and assign the FIRST matching category.

    PRIORITY 1 — "self-harm"
    (a) Content encouraging or depicting self-injury or suicide [any platform, any age], OR
    (b) Mention, promotion, or casual depiction of vaping, e-cigarettes, smoking, or underage drinking ONLY IF: (age = "below 18") OR (platform = "forKids")

    PRIORITY 2 — "hate-speech"
    Hate speech, targeted bullying, harassment, cyberbullying, malicious exclusion, or aggressive insults.

    PRIORITY 3 — "adult-content"
    (a) Explicit material or adult nudity [any platform, any age], OR
    (b) Age-inappropriate themes — romance, dating apps, or suggestive dating content ONLY IF: (age = "below 18") OR (platform = "forKids")

    PRIORITY 4 — "safe"
    Applies when NONE of the above rules are triggered given the audience context.

    [OUTPUT INSTRUCTIONS]
    Return ONLY a single valid JSON object. 
    IMPORTANT: You MUST write the "reasoning" field FIRST to evaluate the rules step-by-step. Then output the post_category based on that reasoning.
    If post_category = "safe", flagged_keywords MUST be [].

    [EXPECTED JSON SCHEMA]
    {{
      "reasoning": "Brief explanation citing the specific rule and condition.",
      "post_category": "safe" | "self-harm" | "hate-speech" | "adult-content",
      "confidence_score": 0.95,
      "flagged_keywords": ["keyword1", "phrase2"]
    }}

    [CURRENT EVALUATION]
    Post: "{post_text}"
    Platform: {platform} | Age: {age}
    """

    return system_prompt.format(platform=platform, age=age, post_text=post_text)


# ==========================================
# 3. GROQ INFERENCE ENGINE
# ==========================================
class GroqModerator:
    def __init__(self, model_id: str = "llama-3.3-70b-versatile"):
        """
        Initializes the Groq client. Requires GROQ_API_KEY in the environment.
        Recommended models: 'llama-3.3-70b-versatile' (smartest) or 'llama3-8b-8192' (fastest).
        """
        api_key = API_KEY
        if not api_key:
            raise ValueError("Please set the GROQ_API_KEY environment variable.")

        print(f"Initializing Groq Inference using model '{model_id}'...")

        self.client = Groq(api_key=api_key)
        self.model_id = model_id

    def evaluate_text(self, text: str, platform: str, age: str) -> Dict[str, Any]:
        """Sends the payload to Groq and extracts the JSON."""
        prompt_content = build_moderation_prompt(text, platform, age)

        try:
            response = self.client.chat.completions.create(
                model=self.model_id,
                response_format={"type": "json_object"}, # Groq fully supports JSON mode
                temperature=0.1, # Low temperature for deterministic behavior
                max_completion_tokens=512, # Enough for reasoning + JSON schema
                messages=[
                    {
                        "role": "system",
                        "content": "You are a precise JSON-only content moderation utility. Output valid JSON matching the user's schema. Do not use markdown blocks."
                    },
                    {
                        "role": "user",
                        "content": prompt_content
                    }
                ]
            )

            raw_output = response.choices[0].message.content

            # Defensive clean up just in case Llama sneaks markdown backticks in
            cleaned_output = raw_output.replace("```json", "").replace("```", "").strip()
            validated_data = ModerationResult.model_validate_json(cleaned_output)

            # Returns a clean, verified Python dictionary matching your required types
            return validated_data.model_dump()


        except Exception as e:
            return {
                "reasoning": f"Groq API or Parsing Error: {str(e)}",
                "post_category": "error",
                "confidence_score": 0.0,
                "flagged_keywords": []
            }