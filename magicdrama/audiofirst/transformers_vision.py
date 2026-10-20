"""Installed publisher VLM transport. Descriptions are not acceptance evidence."""
from pathlib import Path


class TransformersVision:
    def __init__(self,model_path,device='cpu'):
        import torch
        from transformers import AutoProcessor,AutoModelForImageTextToText
        if device not in ('cpu','cuda'):raise ValueError('Only explicit local CPU/CUDA supported')
        path=Path(model_path)
        if not (path/'model.safetensors').is_file():raise ValueError('Installed safetensors model required')
        torch.set_num_threads(2)
        self.torch=torch;self.device=device
        self.processor=AutoProcessor.from_pretrained(str(path),local_files_only=True,trust_remote_code=False,size={'longest_edge':512})
        self.model=AutoModelForImageTextToText.from_pretrained(str(path),local_files_only=True,trust_remote_code=False,
            dtype=torch.float32 if device=='cpu' else torch.bfloat16,attn_implementation='eager').to(device).eval()
    def describe(self,image_path,question='Describe visible actors, clothing, props and their orientation. Do not guess hidden details.'):
        from PIL import Image
        with Image.open(image_path) as source:image=source.convert('RGB')
        if image.width*image.height>20000000:raise ValueError('Image exceeds pixel limit')
        prompt=self.processor.apply_chat_template([{'role':'user','content':[{'type':'image'},{'type':'text','text':question}]}],add_generation_prompt=True)
        inputs=self.processor(text=prompt,images=[image],return_tensors='pt').to(self.device)
        with self.torch.inference_mode():out=self.model.generate(**inputs,max_new_tokens=128,do_sample=False)
        return {'description':self.processor.batch_decode(out[:,inputs['input_ids'].shape[1]:],skip_special_tokens=True)[0],
            'status':'uncalibrated_description_not_acceptance','speech_verified':False,'lip_sync_verified':False}
