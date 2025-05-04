from typing import List, Dict, Optional
from ..models import MergedBlock, TranslatedBlock, Block # Need Block for original bbox
from ..config import get_openai_client, AZURE_OPENAI_DEPLOYMENT_NAME
import time
from openai import RateLimitError, APIError, Timeout, NotFoundError
import re # For parsing the response

# Configuration for batching translation requests
TRANSLATION_BATCH_SIZE = 40 # Number of blocks to translate per API call

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
        # Updated prompt for batch processing
        base_prompt = f"""You are an expert translator. Translate the following numbered English texts to Korean. {tone_instruction} Maintain the original meaning and context.
Return the translations also numbered and separated EXACTLY by '|||' (three pipe characters).
Example Input:
1. Hello world
2. How are you?

Example Output:
1. 안녕하세요 월드 ||| 2. 어떻게 지내세요?
"""

        if glossary:
            glossary_section = "\nUse the following glossary for specific terms (English: Korean):\n"
            for eng, kor in glossary.items():
                glossary_section += f"- '{eng}': '{kor}'\n"
            base_prompt += glossary_section

        base_prompt += "\nTranslate the user's numbered text now:"
        return base_prompt

    def translate_blocks(self, merged_blocks: List[MergedBlock], original_blocks_map: Dict[str, Block]) -> List[TranslatedBlock]:
        """Translates a list of merged text blocks in batches.

        Args:
            merged_blocks: List of MergedBlock objects to translate.
            original_blocks_map: A dictionary mapping original block IDs to Block objects
                                 to retrieve the original bounding box.

        Returns:
            A list of TranslatedBlock objects.
        """
        print(f"[Translator] Starting batched translation for {len(merged_blocks)} blocks (batch size: {TRANSLATION_BATCH_SIZE})...")
        all_translated_data: List[TranslatedBlock] = []
        if not merged_blocks:
            print("[Translator] No blocks to translate.")
            return []

        non_empty_blocks = [block for block in merged_blocks if block.text.strip()]
        if not non_empty_blocks:
             print("[Translator] All blocks are empty after stripping.")
             return []
        
        print(f"[Translator] Translating {len(non_empty_blocks)} non-empty blocks.")

        # Process blocks in batches
        for i in range(0, len(non_empty_blocks), TRANSLATION_BATCH_SIZE):
            batch_blocks = non_empty_blocks[i : i + TRANSLATION_BATCH_SIZE]
            batch_texts = [block.text for block in batch_blocks]

            # Format the request for the batch
            numbered_texts = "\n".join([f"{idx+1}. {text}" for idx, text in enumerate(batch_texts)])
            
            print(f"[Translator] Processing batch {i // TRANSLATION_BATCH_SIZE + 1} ({len(batch_blocks)} blocks)...")

            # Simple retry logic for the batch API call
            max_retries = 3
            retry_delay = 5 # seconds
            request_timeout = 60 # seconds per attempt (increased for potentially larger requests)
            translated_texts_in_batch = []

            for attempt in range(max_retries):
                try:
                    print(f"  Attempt {attempt + 1}/{max_retries}: Calling OpenAI API for batch...")
                    start_api_call = time.time()
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": self.system_prompt},
                            {"role": "user", "content": numbered_texts}
                        ],
                        temperature=0.3,
                        timeout=request_timeout,
                        # max_tokens might be necessary for large batches
                    )
                    api_duration = time.time() - start_api_call
                    raw_response_text = response.choices[0].message.content.strip()
                    print(f"  Attempt {attempt + 1} successful. API call duration: {api_duration:.2f}s.")
                    # print(f" Raw response: {raw_response_text}") # Debug

                    # Parse the combined response
                    # Expecting format like "1. translation1 ||| 2. translation2 ||| ..."
                    parsed_translations = [t.strip() for t in raw_response_text.split('|||')]
                    
                    # Refined parsing to remove the "N. " prefix
                    cleaned_translations = []
                    for t in parsed_translations:
                        # Remove leading number and period, like "1. " or "23. "
                        cleaned = re.sub(r"^\d+\.\s*", "", t).strip()
                        cleaned_translations.append(cleaned)

                    if len(cleaned_translations) == len(batch_blocks):
                        translated_texts_in_batch = cleaned_translations
                        print(f"  Successfully parsed {len(translated_texts_in_batch)} translations from batch response.")
                        break # Exit retry loop on success
                    else:
                        print(f"  Warning: Mismatch after parsing batch response. Expected {len(batch_blocks)}, got {len(cleaned_translations)}. Raw response: '{raw_response_text}'")
                        if attempt == max_retries - 1:
                             print(f"  Failed to parse response correctly after {max_retries} attempts. Skipping batch.")
                             # Decide: skip batch or fall back to individual translation? Skipping for now.
                        else:
                             print(f"  Retrying batch due to parsing mismatch...")
                             time.sleep(retry_delay)
                             retry_delay *= 1.5


                # --- Exception Handling (same as before, but applied to batch) ---
                except NotFoundError as e:
                    print(f"OpenAI Error: Resource not found (404) during batch processing. Please check AZURE_OPENAI_DEPLOYMENT_NAME. Details: {e}")
                    raise e
                except RateLimitError as e:
                    print(f"Rate limit error during batch processing: {e}. Retrying in {retry_delay}s... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                except Timeout as e:
                    print(f"Timeout error during batch processing after {request_timeout}s: {e}. Retrying in {retry_delay}s... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay *= 1.5
                except APIError as e:
                    print(f"API error during batch processing (Status: {e.status_code}): {e}. Retrying in {retry_delay}s... (Attempt {attempt + 1}/{max_retries})")
                    if e.status_code == 400:
                        print("Potential content filter issue or invalid request in batch. Skipping batch.")
                        break # Don't retry bad requests
                    time.sleep(retry_delay)
                    retry_delay *= 2
                except Exception as e:
                    print(f"Unexpected error during batch processing: {e}")
                    import traceback
                    print(f"Traceback: {traceback.format_exc()}")
                    break # Skip batch on unexpected error
            else: # This else belongs to the 'for attempt' loop
                print(f"Failed to translate batch starting with block '{batch_blocks[0].id}' after {max_retries} attempts due to API errors or parsing issues.")
                print("Falling back to individual translation for this batch.")
                # --- Fallback to individual translation --- 
                for block_in_batch in batch_blocks:
                     individual_translated_text = self._translate_single_block_with_retry(block_in_batch)
                     if individual_translated_text is not None:
                         first_original_id = block_in_batch.original_block_ids[0]
                         original_block = original_blocks_map.get(first_original_id)
                         if original_block:
                             all_translated_data.append(TranslatedBlock(
                                id=block_in_batch.id,
                                original_text=block_in_batch.text,
                                translated_text=individual_translated_text,
                                bbox=original_block.bbox,
                                page_number=block_in_batch.page_number
                            ))
                         else:
                             print(f"Warning (Fallback): Could not find original block {first_original_id} for bbox for merged block {block_in_batch.id}.")
                     # else: # Error message already printed in _translate_single_block_with_retry
                         # pass
                # --- End Fallback --- 
                continue # Move to the next batch

            # If translation was successful for the batch, create TranslatedBlock objects
            if translated_texts_in_batch: # This check is important
                 for original_m_block, translated_text in zip(batch_blocks, translated_texts_in_batch):
                    first_original_id = original_m_block.original_block_ids[0]
                    original_block = original_blocks_map.get(first_original_id)
                    if original_block:
                         all_translated_data.append(TranslatedBlock(
                            id=original_m_block.id,
                            original_text=original_m_block.text,
                            translated_text=translated_text,
                            bbox=original_block.bbox,
                            page_number=original_m_block.page_number
                        ))
                         # print(f"  Added translated block: {original_m_block.id} -> {translated_text[:30]}...") # Debug
                    else:
                        print(f"Warning: Could not find original block {first_original_id} for bbox for merged block {original_m_block.id}.")

        print(f"[Translator] Finished batched translation. Returning {len(all_translated_data)} translated blocks.")
        return all_translated_data

    def _translate_single_block_with_retry(self, block: MergedBlock) -> Optional[str]:
        """Translates a single block with retry logic. Helper for fallback."""
        max_retries = 3
        retry_delay = 2
        request_timeout = 30
        text_to_translate = block.text

        # Build a simpler prompt for single translation
        single_prompt = self.system_prompt.split("Return the translations also numbered")[0] # Remove batch instructions
        single_prompt += "\nTranslate the user's text now:"

        for attempt in range(max_retries):
            try:
                print(f"  Fallback Attempt {attempt + 1}/{max_retries}: Translating block {block.id} individually...")
                start_api_call = time.time()
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": single_prompt},
                        {"role": "user", "content": text_to_translate}
                    ],
                    temperature=0.3,
                    timeout=request_timeout,
                )
                api_duration = time.time() - start_api_call
                translated_text = response.choices[0].message.content.strip()
                print(f"  Fallback translation for block {block.id} successful in {api_duration:.2f}s.")
                return translated_text
            except NotFoundError as e:
                 print(f"OpenAI Error (Fallback): Resource not found (404). Block {block.id}. Check config. Details: {e}")
                 raise e # Still raise this, likely a config error
            except RateLimitError as e:
                 print(f"Rate limit error (Fallback) block {block.id}: {e}. Retrying in {retry_delay}s... (Attempt {attempt + 1}/{max_retries})")
                 time.sleep(retry_delay)
                 retry_delay *= 2
            except Timeout as e:
                 print(f"Timeout error (Fallback) block {block.id}: {e}. Retrying in {retry_delay}s... (Attempt {attempt + 1}/{max_retries})")
                 time.sleep(retry_delay)
                 retry_delay *= 1.5
            except APIError as e:
                 print(f"API error (Fallback) block {block.id} (Status: {e.status_code}): {e}. Retrying... (Attempt {attempt + 1}/{max_retries})")
                 if e.status_code == 400:
                     print("Potential content filter/invalid request (Fallback). Skipping block.")
                     break
                 time.sleep(retry_delay)
                 retry_delay *= 2
            except Exception as e:
                 print(f"Unexpected error (Fallback) translating block {block.id}: {e}")
                 break
        else:
             print(f"Failed to translate block {block.id} individually after {max_retries} attempts.")
             return None

    # Glossary preprocessing removed as it's now part of the system prompt
    # def _apply_glossary_preprocessing(self, text: str) -> str: ...

    def update_settings(self, translate_tone: Optional[str] = None, glossary: Optional[Dict[str, str]] = None):
        """Allows updating translator settings after initialization."""
        updated_tone = translate_tone or ("formal" if "formally" in self.system_prompt else "friendly")
        
        if glossary is not None:
            self.glossary = glossary
            print(f"Translator glossary updated: {len(glossary)} terms.")
        
        # Rebuild system prompt with potentially new tone and glossary
        # Ensure the prompt includes batch instructions
        self.system_prompt = self._build_default_system_prompt(updated_tone, self.glossary)
        print(f"Translator settings updated. Tone: {updated_tone}. System prompt regenerated for batch processing.")
        # print(f"New system prompt: {self.system_prompt}") # Optional: for debugging 