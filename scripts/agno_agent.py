from dotenv import load_dotenv

# Load environment variables from .env here, so that they're available for models
load_dotenv()
from agno.models.anthropic.claude import Claude
from agno.models.google.gemini import Gemini
from agno.models.openai.chat import OpenAIChat
from agno.models.openrouter.openrouter import OpenRouter
from agno.playground.playground import Playground
from agno.playground.serve import serve_playground_app
from sensai.util import logging
from sensai.util.helper import mark_used

from serena.agno import SerenaAgnoAgentProvider

mark_used(Claude, Gemini, OpenAIChat, OpenRouter)

# initialize logging (Note: since this module is reimported by serve_playground_app and the logging configuration
# is extended by SerenaAgentProvider, we must handle this here conditionally)
if __name__ == "__main__":
    logging.configure(level=logging.INFO)

# Define the model to use (see Agno documentation for supported models; these are just examples)
# model = Claude(id="claude-3-7-sonnet-20250219")
# model = Gemini(id="gemini-2.5-pro-exp-03-25")
# If you fail to specify `.env` OPENROUTER_API_KEY, Agno will attempt to use OPENAI_API_KEY
model = OpenRouter(id="google/gemini-2.0-flash-001")
memory_model = OpenRouter(id="openai/gpt-4.1")

app = Playground(agents=[SerenaAgnoAgentProvider.get_agent(model, memory_model)]).get_app()

if __name__ == "__main__":
    # add host="0.0.0.0" for use with docker; i.e. sharing port 7777 to host
    serve_playground_app("agno_agent:app", reload=False, log_config=None)
