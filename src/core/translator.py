from typing import List, Dict, Optional
from ..models import MergedBlock, TranslatedBlock, Block # Need Block for original bbox
from ..config import get_openai_client, AZURE_OPENAI_DEPLOYMENT_NAME
import time
from openai import RateLimitError, APIError, Timeout

class Translator:
    """Translates text blocks using Azure OpenAI via the openai library."""

    def __init__(self, model: str = AZURE_OPENAI_DEPLOYMENT_NAME,
                 system_prompt: Optional[str] = None,
                 translate_tone: str = "formal", # e.g., "formal", "friendly"
                 glossary: Optional[Dict[str, str]] = None):
        self.client = get_openai_client()
        self.model = model
        self.glossary = glossary or {}
        # Build system prompt after glossary is set
        self.system_prompt = system_prompt or self._build_default_system_prompt(translate_tone, self.glossary)
        

    def _build_default_system_prompt(self, tone: str, glossary: Dict[str, str]) -> str:
        tone_instruction = "Translate formally and accurately." if tone == "formal" else "Translate in a friendly and natural tone."
        base_prompt = f"You are an expert translator. Translate the following English text to Korean. {tone_instruction} Maintain the original meaning and context."
        
        if glossary:
            glossary_section = "\n\nUse the following glossary for specific terms (English: Korean):\n"
            for eng, kor in glossary.items():
                glossary_section += f"- '{eng}': '{kor}'\n"
            base_prompt += glossary_section
            base_prompt += "\nTranslate the user's text now:"

        return base_prompt

    def translate_blocks(self, merged_blocks: List[MergedBlock], original_blocks_map: Dict[str, Block]) -> List[TranslatedBlock]:
        """Translates a list of merged text blocks.

        Args:
            merged_blocks: List of MergedBlock objects to translate.
            original_blocks_map: A dictionary mapping original block IDs to Block objects
                                 to retrieve the original bounding box.

        Returns:
            A list of TranslatedBlock objects.
        """
        translated_data: List[TranslatedBlock] = []
        if not merged_blocks:
            return []

        # Group blocks slightly to potentially reduce API calls (simple approach)
        # A more robust approach would consider token limits per request.
        # Let's translate block by block for simplicity now.
        for m_block in merged_blocks:
            text_to_translate = m_block.text # Glossary is now in system prompt
            if not text_to_translate.strip():
                print(f"Skipping empty block {m_block.id}")
                continue

            # Simple retry logic
            max_retries = 3
            retry_delay = 5 # seconds
            request_timeout = 30 # seconds per attempt
            
            for attempt in range(max_retries):
                try:
                    print(f"Translating block {m_block.id} (len: {len(text_to_translate)}, attempt {attempt + 1})...")
                    start_api_call = time.time()
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": self.system_prompt},
                            {"role": "user", "content": text_to_translate}
                        ],
                        temperature=0.3,
                        timeout=request_timeout,
                        # max_tokens can be set to prevent overly long responses
                    )
                    api_duration = time.time() - start_api_call
                    translated_text = response.choices[0].message.content.strip()
                    print(f"Block {m_block.id} translated successfully in {api_duration:.2f}s.")

                    # Find the bounding box from the *first* original block
                    first_original_id = m_block.original_block_ids[0]
                    original_block = original_blocks_map.get(first_original_id)

                    if original_block:
                         translated_data.append(TranslatedBlock(
                            id=m_block.id,
                            original_text=m_block.text,
                            translated_text=translated_text,
                            bbox=original_block.bbox,
                            page_number=m_block.page_number
                        ))
                    else:
                        print(f"Warning: Could not find original block {first_original_id} for bbox.")

                    break # Exit retry loop on success

                except RateLimitError as e:
                    print(f"Rate limit error translating block {m_block.id}: {e}. Retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                except Timeout as e:
                    print(f"Timeout error translating block {m_block.id} after {request_timeout}s: {e}. Retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 1.5 # Less aggressive backoff for timeout
                except APIError as e:
                    print(f"API error translating block {m_block.id} (Status: {e.status_code}): {e}. Retrying in {retry_delay}s...")
                    # Specific handling for common errors
                    if e.status_code == 400: # Bad request (e.g., content filter)
                         print("Potential content filter issue or invalid request. Skipping block.")
                         break # Don't retry bad requests usually
                    time.sleep(retry_delay)
                    retry_delay *= 2
                except Exception as e:
                    print(f"Unexpected error translating block {m_block.id}: {e}")
                    break # Skip block on unexpected error
            else:
                 print(f"Failed to translate block {m_block.id} after {max_retries} attempts.")

        return translated_data

    # Glossary preprocessing removed as it's now part of the system prompt
    # def _apply_glossary_preprocessing(self, text: str) -> str: ...

    def update_settings(self, translate_tone: Optional[str] = None, glossary: Optional[Dict[str, str]] = None):
        """Allows updating translator settings after initialization."""
        updated_tone = translate_tone or ("formal" if "formally" in self.system_prompt else "friendly")
        
        if glossary is not None:
            self.glossary = glossary
            print(f"Translator glossary updated: {len(glossary)} terms.")
        
        # Rebuild system prompt with potentially new tone and glossary
        self.system_prompt = self._build_default_system_prompt(updated_tone, self.glossary)
        print(f"Translator settings updated. Tone: {updated_tone}. System prompt regenerated.")
        # print(f"New system prompt: {self.system_prompt}") # Optional: for debugging 