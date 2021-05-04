import torch
import random
import numpy as np

import time
import torch
import numpy as np
from nlp import load_metric
import pytorch_lightning as pl
from torch.utils.data import DataLoader
from typing import Callable, Dict, Iterable, List, Tuple, Union
from dataset import get_dataset

from transformers import (
    AdamW,
    T5ForConditionalGeneration,
    T5Tokenizer,
    get_linear_schedule_with_warmup
)

class T5FineTuner(pl.LightningModule):
    def __init__(self, hparams) -> None:
        super(T5FineTuner, self).__init__()
        self.hparams = hparams        
        self.model = T5ForConditionalGeneration.from_pretrained(hparams.model_name)
        self.tokenizer = T5Tokenizer.from_pretrained(hparams.tokenizer_name)
        
        if self.hparams.freeze_embeds:
            self.freeze_embeds()
        if self.hparams.freeze_encoder:
            self.freeze_params(self.model.get_encoder())
            self.assert_all_frozen(self.model.get_encoder())
            
            
        self.new_special_tokens = ['<',
                                   '<ARG-DRUG>',
                                   '<ARG-CONDITION>',
                                   '<ARG-GENDER>',
                                   '<ARG-RACE>',
                                   '<ARG-ETHNICITY>',
                                   '<ARG-STATE>',
                                   '<ARG-AGE>',
                                   '<ARG-TIMEDAYS>',
                                   '<ARG-TIMEYEARS>',
                                   '<GENDER-TEMPLATE>', 
                                   '<RACE-TEMPLATE>', 
                                   '<ETHNICITY-TEMPLATE>', 
                                   '<STATEID-TEMPLATE>', 
                                   '<CONDITION-TEMPLATE>',
                                   '<DRUG-TEMPLATE>',
                                   '<ARG-CONDITION>', 
                                   '<STATENAME-TEMPLATE>',
                                   '<ARG-DRUG>', 
                                   '<ARG-DAYS>'] + [f'<{i}>' for i in range(10)]
        
#         additional_special_tokens = self.tokenizer.additional_special_tokens + self.new_special_tokens        
#         self.tokenizer.add_special_tokens({'additional_special_tokens': additional_special_tokens})

        num_added_toks = self.tokenizer.add_special_tokens({'additional_special_tokens': self.new_special_tokens})
        self.model.resize_token_embeddings(len(self.tokenizer))
        
        
        n_observations_per_split = {
            "train": self.hparams.n_train,
            "validation": self.hparams.n_val,
            "test": self.hparams.n_test,
        }
        self.n_obs = {k: v if v >= 0 else None for k, v in n_observations_per_split.items()}
        
    
    def freeze_params(self, model):
        for par in model.parameters():
            par.requires_grad = False
            
            
    def freeze_embeds(self):
        """Freeze token embeddings and positional embeddings for bart, just token embeddings for t5."""
        try:
            self.freeze_params(self.model.model.shared)
            for d in [self.model.model.encoder, self.model.model.decoder]:
                self.freeze_params(d.embed_positions)
                self.freeze_params(d.embed_tokens)
        except AttributeError:
            self.freeze_params(self.model.shared)
            for d in [self.model.encoder, self.model.decoder]:
                self.freeze_params(d.embed_tokens)
    
    def lmap(self, f: Callable, x: Iterable) -> List:
        """list(map(f, x))"""
        return list(map(f, x))

    def assert_all_frozen(self, model):
        model_grads: List[bool] = list(self.grad_status(model))
        n_require_grad = sum(self.lmap(int, model_grads))
        npars = len(model_grads)
        assert not any(model_grads), f"{n_require_grad/npars:.1%} of {npars} weights require grad"

    def is_logger(self):
        return self.trainer.global_rank  <= 0
    
    
    def parse_score(self, result):
        return {k: round(v.mid.fmeasure * 100, 4) for k, v in result.items()}
        
    def forward(
      self, input_ids, attention_mask=None, decoder_input_ids=None, decoder_attention_mask=None, labels=None
  ):
        return self.model(
            input_ids,
            attention_mask=attention_mask,
            decoder_input_ids=decoder_input_ids,
            decoder_attention_mask=decoder_attention_mask,
            labels=labels,
    )

    def _step(self, batch):
        labels = batch["target_ids"]
        labels[labels[:, :] == self.tokenizer.pad_token_id] = -100

        outputs = self(
            input_ids=batch["source_ids"],
            attention_mask=batch["source_mask"],
            labels=labels,
            decoder_attention_mask=batch['target_mask']
        )

        loss = outputs[0]

        return loss
    
    
    def ids_to_clean_text(self, generated_ids):
        gen_text = self.tokenizer.batch_decode(
            generated_ids, skip_special_tokens=False, clean_up_tokenization_spaces=True
        )
        return self.lmap(str.strip, gen_text)
    
    
    def _generative_step(self, batch) :
        
        t0 = time.time()
        
        generated_ids = self.model.generate(
            batch["source_ids"],
            attention_mask=batch["source_mask"],
            use_cache=True,
            decoder_attention_mask=batch['target_mask'],
            max_length=self.hparams.max_output_length, 
            num_beams=2,
            repetition_penalty=2.5, 
            length_penalty=1.0, 
            early_stopping=self.hparams.early_stop_callback
        )
        preds = self.ids_to_clean_text(generated_ids)
        target = self.ids_to_clean_text(batch["target_ids"])
            
        gen_time = (time.time() - t0) / batch["source_ids"].shape[0]  
    
        loss = self._step(batch)
        base_metrics = {'val_loss': loss}
        summ_len = np.mean(self.lmap(len, generated_ids))
        base_metrics.update(gen_time=gen_time, gen_len=summ_len, preds=preds, target=target)

        
        return base_metrics
    

    def training_step(self, batch, batch_idx):
        loss = self._step(batch)
        
        self.log('train_loss', loss, on_step=True, on_epoch=True, prog_bar=True)

        tensorboard_logs = {"loss": loss}
        return loss # {"loss": loss, "log": tensorboard_logs}
  

    def validation_step(self, batch, batch_idx):
        
        return self._generative_step(batch)
    
  
    def validation_epoch_end(self, outputs):

        avg_loss = torch.stack([x["val_loss"] for x in outputs]).mean()
        tensorboard_logs = {"val_loss": avg_loss}
                
        self.target_gen= []
        self.prediction_gen=[]
        
        self.log('val_loss', avg_loss, on_epoch=True, prog_bar=True)
        
        return None

    
    def configure_optimizers(self):

        "Prepare optimizer and schedule (linear warmup and decay)"
        model = self.model
        no_decay = ["bias", "LayerNorm.weight"]
        optimizer_grouped_parameters = [
            {
                "params": [p for n, p in model.named_parameters() if not any(nd in n for nd in no_decay)],
                "weight_decay": self.hparams.weight_decay,
            },
            {
                "params": [p for n, p in model.named_parameters() if any(nd in n for nd in no_decay)],
                "weight_decay": 0.0,
            },
        ]
        optimizer = AdamW(optimizer_grouped_parameters, lr=self.hparams.learning_rate, eps=self.hparams.adam_epsilon)
        self.opt = optimizer
        return [optimizer]

    def train_dataloader(self):   
        n_samples = self.n_obs['train']
        train_dataset = get_dataset(tokenizer=self.tokenizer, data_split="train", num_samples=n_samples, args=self.hparams)
        dataloader = DataLoader(train_dataset, batch_size=self.hparams.train_batch_size, drop_last=True, shuffle=True, num_workers=24)
        t_total = (
            (len(dataloader.dataset) // (self.hparams.train_batch_size * max(1, self.hparams.n_gpu)))
            // self.hparams.gradient_accumulation_steps
            * float(self.hparams.num_train_epochs)
        )
        scheduler = get_linear_schedule_with_warmup(
            self.opt, num_warmup_steps=self.hparams.warmup_steps, num_training_steps=t_total
        )
        self.lr_scheduler = scheduler
        return dataloader

    def val_dataloader(self):
        n_samples = self.n_obs['validation']
        validation_dataset = get_dataset(tokenizer=self.tokenizer, data_split="validation", num_samples=n_samples, args=self.hparams)
        
        return DataLoader(validation_dataset, batch_size=self.hparams.eval_batch_size, num_workers=24)
    
    
    def test_dataloader(self):
        n_samples = self.n_obs['test']
        test_dataset = get_dataset(tokenizer=self.tokenizer, data_split="test", num_samples=n_samples, args=self.hparams)
        
        return DataLoader(test_dataset, batch_size=self.hparams.eval_batch_size, num_workers=24)
    
    
def set_seed(seed):
    """Seed random seed if needed."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)