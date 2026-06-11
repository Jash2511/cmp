import os
import json
from typing import Dict, Any
from groq import Groq

# ==========================================
# 1. OPTIMIZED PROMPT GENERATOR
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
# 2. GROQ INFERENCE ENGINE
# ==========================================
class GroqModerator:
    def __init__(self, model_id: str = "llama-3.3-70b-versatile"):
        """
        Initializes the Groq client. Requires GROQ_API_KEY in the environment.
        Recommended models: 'llama-3.3-70b-versatile' (smartest) or 'llama3-8b-8192' (fastest).
        """
        api_key = ""
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
            
            return json.loads(cleaned_output)
            
        except Exception as e:
            return {
                "reasoning": f"Groq API or Parsing Error: {str(e)}",
                "post_category": "error",
                "confidence_score": 0.0,
                "flagged_keywords": []
            }


# ==========================================
# 3. VERIFICATION PIPELINE RUN
# ==========================================
if __name__ == "__main__":
    moderator = GroqModerator()

    test_cases = [
        {
            "label": "Minor + Vaping + Dating (Should → self-harm via Priority 1b)",
            "text": "I bought a cool vape kit today and we're planning a wild dating night.",
            "platform": "forKids",
            "age": "below 18"
        },
        {
            "label": "Adult + Vaping + Dating (Should → safe)",
            "text": "I bought a cool vape kit today and we're planning a wild dating night.",
            "platform": "notForKids",
            "age": "above 18"
        },
        {
            "label": "Hate speech (Should → hate-speech via Priority 2)",
            "text": "People like you are disgusting and should disappear.",
            "platform": "general",
            "age": "above 18"
        },
        {
            "label": "Clean post (Should → safe)",
            "text": "Just finished a 10km run. Feeling amazing!",
            "platform": "general",
            "age": "above 18"
        }
    ]

    for case in test_cases:
        print(f"\n--- {case['label']} ---")
        result = moderator.evaluate_text(
            text=case["text"],
            platform=case["platform"],
            age=case["age"]
        )
        print(json.dumps(result, indent=2))