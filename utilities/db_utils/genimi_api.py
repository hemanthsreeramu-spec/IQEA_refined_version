import os
import openai
from dotenv import load_dotenv
load_dotenv()
source = "gemini"
# Set environment variables

os.environ["OPENAI_API_KEY"] = os.getenv("GEMINI_API_KEY")
os.environ["OPENAI_API_BASE"] = os.getenv("GEMINI_ENDPOINT")
client = openai.OpenAI(api_key =  os.environ["OPENAI_API_KEY"],
                       base_url = os.environ["OPENAI_API_BASE"])


def get_queries_from_ai_updated_gemini(formatted_summary):
    # Access the variables
    model = "gemini-2.5-pro"
    response = client.chat.completions.create(model=model,
                                          messages=[{
                                                     "content": formatted_summary
                                                     }
                                                    ])
    print(response.choices[0].message.content)
    return response.choices[0].message.content
formatted_summary="7 wonders name?"

get_queries_from_ai_updated_gemini(formatted_summary)