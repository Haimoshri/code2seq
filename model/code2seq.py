from typing import Tuple, Dict, List

import torch
import torch.nn.functional as F
from pytorch_lightning.core.lightning import LightningModule
from torch.optim import Adam, Optimizer
from torch.utils.data import DataLoader

from configs import Code2SeqConfig
from dataset import Vocabulary
from dataset.path_context_dataset import PathContextDataset, collate_path_contexts
from model.modules import PathEncoder, PathDecoder
from utils.common import PAD, SOS


class Code2Seq(LightningModule):
    def __init__(self, config: Code2SeqConfig, vocab: Vocabulary):
        super().__init__()
        self.config = config
        self.label_pad_id = vocab.label_to_id[PAD]

        encoder_config = self.config.encoder
        decoder_config = self.config.decoder
        self.encoder = PathEncoder(
            encoder_config,
            decoder_config.decoder_size,
            len(vocab.token_to_id),
            vocab.token_to_id[PAD],
            len(vocab.type_to_id),
            vocab.type_to_id[PAD],
        )
        self.decoder = PathDecoder(
            decoder_config, len(vocab.label_to_id), vocab.label_to_id[SOS], vocab.label_to_id[PAD]
        )

    def forward(self, samples: Dict[str, torch.Tensor], paths_for_label: List[int], output_length: int) -> torch.Tensor:
        return self.decoder(self.encoder(samples), paths_for_label, output_length)

    def configure_optimizers(self) -> Optimizer:
        return Adam(self.parameters(), self.config.learning_rate)

    def _calculate_loss(self, logits: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
        """ Calculate cross entropy loss.

        :param logits: [seq length; batch size; vocab size]
        :param labels: [seq length; batch size]
        :return: [1]
        """
        # [(seq length - 1) * batch size; vocab size]
        logits = logits[1:].view(-1, logits.shape[-1])
        # [(seq length - 1) * batch size]
        labels = labels[1:].view(-1)
        loss = F.cross_entropy(logits.view(-1, logits.shape[-1]), labels.view(-1), ignore_index=self.label_pad_id)
        return loss

    # ===== TRAIN BLOCK =====

    def train_dataloader(self) -> DataLoader:
        dataset = PathContextDataset(self.config.train_data_path, self.config.shuffle_data)
        data_loader = DataLoader(dataset, batch_size=self.config.batch_size, collate_fn=collate_path_contexts)
        return data_loader

    def training_step(self, batch: Tuple[Dict[str, torch.Tensor], torch.Tensor, List[int]], batch_idx: int) -> Dict:
        paths, labels, paths_for_label = batch

        # [seq length; batch size; vocab size]
        logits = self(paths, paths_for_label, labels.shape[0])
        loss = self._calculate_loss(logits, labels)

        log = {
            "loss": loss,
        }
        return {"loss": loss, "log": log}

    # ===== VALIDATION BLOCK =====

    def val_dataloader(self) -> DataLoader:
        dataset = PathContextDataset(self.config.val_data_path, False)
        data_loader = DataLoader(
            dataset, batch_size=self.config.test_batch_size, collate_fn=collate_path_contexts, num_workers=4
        )
        return data_loader

    def validation_step(self, batch: Tuple[Dict[str, torch.Tensor], torch.Tensor, List[int]], batch_idx: int) -> Dict:
        paths, labels, paths_for_label = batch
        print(len(paths_for_label))

        # [seq length; batch size; vocab size]
        logits = self(paths, paths_for_label, labels.shape[0])
        loss = self._calculate_loss(logits, labels)

        log = {
            "val_loss": loss,
        }
        return {"val_loss": loss, "log": log}

    def validation_epoch_end(self, outputs: List[Dict]) -> Dict:
        pass

    # ===== TEST BLOCK =====

    def test_dataloader(self) -> DataLoader:
        dataset = PathContextDataset(self.config.test_data_path, False)
        data_loader = DataLoader(dataset, batch_size=self.config.test_batch_size, collate_fn=collate_path_contexts)
        return data_loader

    def test_step(self, batch: Tuple[Dict[str, torch.Tensor], torch.Tensor], batch_idx: int) -> Dict:
        pass

    def test_epoch_end(self, outputs: List[Dict]) -> Dict:
        pass
