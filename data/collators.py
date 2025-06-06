import torch

class VQACollator(object):  # Visual Question Answering Collator
    def __init__(self, tokenizer, max_length, mp_image_token_length):
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.mp_image_token_length = mp_image_token_length

        self.image_token_str = tokenizer.image_token
    
    def __call__(self, batch):
        images = [item["image"] for item in batch]
        texts = [item["text_data"] for item in batch]
        answers = [item["answer"] for item in batch]

        # Stack images
        images = torch.stack(images)

        # Create inputs by concatenating special image tokens, question, and answer
        input_sequences = []
        for i in range(len(texts)):
            # Construct the image token segment string
            input_sequences.append(f"{self.image_token_str * self.mp_image_token_length}{texts[i]}{answers[i]}")

        encoded_full_sequences = self.tokenizer.batch_encode_plus(
            input_sequences,
            padding="max_length",
            padding_side="left",
            return_tensors="pt",
            truncation=True,
            max_length=self.max_length,
        )

        # Create labels where only answer tokens are predicted
        input_ids = encoded_full_sequences["input_ids"]
        attention_mask = encoded_full_sequences["attention_mask"]
        labels = input_ids.clone()
        labels[:, :-1] = input_ids[:, 1:].clone() # Shift labels for causal LM
        labels[:, -1] = -100 # Last token has no target

        # Determine original lengths before padding/truncation to handle truncation cases
        original_lengths = [len(self.tokenizer.encode(seq)) for seq in input_sequences]

        for i in range(len(batch)):
            # Case 1: If sequence was truncated (original is longer than max_length)
            if original_lengths[i] > self.max_length:
                labels[i, :] = -100 # Ignore this sample entirely
                # print(f"Sample {i} truncated: original length {original_lengths[i]} exceeds max_length {self.max_length}. Ignoring sample.")
                continue
            
            # Case 2: Sequence fits within max_length
            # Determine the length of the question part for this sample
            question_part_length = len(self.tokenizer.encode(texts[i], add_special_tokens=False))
            
            # Find the position of the first actual token (non-padding)
            # attention_mask might be all zeros if the sequence is fully truncated (handled above) or empty.
            # Ensure there's at least one non-padding token to avoid errors with .nonzero().
            if attention_mask[i].sum() == 0: # Should not happen if not truncated and not empty.
                labels[i, :] = -100 # Defensive: if no actual tokens, ignore sample
                continue
            
            first_token_pos = attention_mask[i].nonzero(as_tuple=True)[0][0].item()
            
            # The total length of the "prompt" part (special image tokens + question)
            total_prompt_length = self.mp_image_token_length + question_part_length
            
            # Mask labels for padding tokens (before first_token_pos) and the entire prompt part.
            # The prompt part starts at first_token_pos and has length total_prompt_length.
            # So, tokens from index 0 up to (first_token_pos + total_prompt_length - 1) should be masked.
            # The slicing labels[i, :N] masks indices 0 to N-1.
            mask_until_idx = first_token_pos + total_prompt_length - 1
            labels[i, :mask_until_idx] = -100

        return {
            "image": images,
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "labels": labels
        }

class MMStarCollator(object):  # https://huggingface.co/datasets/Lin-Chen/MMStar
    def __init__(self, tokenizer, mp_image_token_length):
        self.tokenizer = tokenizer
        self.mp_image_token_length = mp_image_token_length

        self.image_token_str = tokenizer.image_token
    
    def __call__(self, batch):
        images = [item["image"] for item in batch]
        questions = [item["text_data"] for item in batch]
        answers = [item["answer"] for item in batch]

        # Stack images
        images = torch.stack(images)

        # Create input sequences with image placeholders
        question_sequences = []
        for question_text in questions:
            question_sequences.append(f"{self.image_token_str * self.mp_image_token_length}{question_text}")
        
        
        encoded_question_sequences = self.tokenizer.batch_encode_plus(
            question_sequences,
            padding=True,
            padding_side="left",
            return_tensors="pt"
        )

        encoded_answer_sequences = self.tokenizer.batch_encode_plus(
            answers,
            padding=True,
            padding_side="left",
            return_tensors="pt"
        )
        
        return {
            "images": images,
            "input_ids": encoded_question_sequences['input_ids'],
            "attention_mask": encoded_question_sequences['attention_mask'],
            "labels": encoded_answer_sequences['input_ids'],
        }