### Role of aiAnalizer.py 
- It takes json and gives out json. Input json contains user post and metadata. Output json contains content moderations related feilds.

### How to run this file? 
```bash
mkdir cmp
cd cmp
git clone https://github.com/ChampDeepak/cmp
python3 -m venv .venv
source .venv/bin/activate
pip install groq
python3 aiAnalizer.py
```

### Next tasks 
1. Setup api gateway that takes json and adds to redis messaging queue.
2. Setup worker that consumes events from queue and processes them using aiAnalizer.py and notifies admin and saves the response to db.

### Note 
- Use separate branch for development and merge to main branch only after testing. 
