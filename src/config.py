import os
from dotenv import load_dotenv
from openai import AzureOpenAI

# Load environment variables from .env file
load_dotenv()

# Azure Document Intelligence Config
AZURE_DI_ENDPOINT = os.getenv("AZURE_DI_ENDPOINT")
AZURE_DI_KEY = os.getenv("AZURE_DI_KEY")

# Azure OpenAI Config (for openai library v1+)
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01") # Default if not set

# --- OpenAI Client Initialization (using Azure settings) ---
def get_openai_client():
    """Initializes and returns the AzureOpenAI client."""
    if not all([AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT_NAME]):
        raise ValueError("Azure OpenAI environment variables are not fully set.")

    client = AzureOpenAI(
        api_key=AZURE_OPENAI_API_KEY,
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_version=AZURE_OPENAI_API_VERSION
    )
    return client

# --- Validation ---
def validate_config():
    """Checks if all required configuration variables are loaded."""
    required_di = [AZURE_DI_ENDPOINT, AZURE_DI_KEY]
    required_aoai = [AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT_NAME]

    if not all(required_di):
        print("Warning: Azure Document Intelligence environment variables missing.")
        # Depending on usage, might want to raise an error

    if not all(required_aoai):
        print("Warning: Azure OpenAI environment variables missing.")
        # Depending on usage, might want to raise an error

# Validate configuration on import
validate_config() 