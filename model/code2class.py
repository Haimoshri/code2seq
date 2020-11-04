from typing import Dict, List, Tuple

import torch
import torch.nn.functional as F
from pytorch_lightning import LightningModule
from pytorch_lightning.metrics.functional import confusion_matrix
from torch.optim import Optimizer
from torch.optim.lr_scheduler import _LRScheduler

from configs import Code2ClassConfig
from dataset import PathContextBatch
from model.modules import PathEncoder, PathClassifier
from utils.common import PAD
from utils.training import configure_optimizers_alon
from utils.vocabulary import Vocabulary


class Code2Class(LightningModule):
    def __init__(self, config: Code2ClassConfig, vocabulary: Vocabulary):
        super().__init__()
        self._config = config
        self.save_hyperparameters()
        self.encoder = PathEncoder(
            self._config.encoder_config,
            self._config.classifier_config.classifier_input_size,
            len(vocabulary.token_to_id),
            vocabulary.token_to_id[PAD],
            len(vocabulary.type_to_id),
            vocabulary.type_to_id[PAD],
        )
        self.num_classes = len(vocabulary.label_to_id)
        self.classifier = PathClassifier(self._config.classifier_config, self.num_classes)

    def configure_optimizers(self) -> Tuple[List[Optimizer], List[_LRScheduler]]:
        return configure_optimizers_alon(self._config.hyper_parameters, self.parameters())

    def forward(self, samples: Dict[str, torch.Tensor], paths_for_label: List[int]) -> torch.Tensor:  # type: ignore
        return self.classifier(self.encoder(samples), paths_for_label)

    # ========== MODEL STEP ==========

    def training_step(self, batch: PathContextBatch, batch_idx: int) -> Dict:  # type: ignore
        # [batch size; num_classes]
        logits = self(batch.contexts, batch.contexts_per_label)
        loss = F.cross_entropy(logits, batch.labels.squeeze(0))
        log = {"train/loss": loss}
        with torch.no_grad():
            conf_matrix = confusion_matrix(logits.argmax(-1), batch.labels.squeeze(0))
            log["train/accuracy"] = conf_matrix.trace() / conf_matrix.sum()
        self.log_dict(log)

        return {"loss": loss, "confusion_matrix": conf_matrix}

    def validation_step(self, batch: PathContextBatch, batch_idx: int) -> Dict:  # type: ignore
        # [batch size; num_classes]
        logits = self(batch.contexts, batch.contexts_per_label)
        loss = F.cross_entropy(logits, batch.labels.squeeze(0))
        with torch.no_grad():
            conf_matrix = confusion_matrix(logits.argmax(-1), batch.labels.squeeze(0))

        return {"loss": loss, "confusion_matrix": conf_matrix}

    def test_step(self, batch: PathContextBatch, batch_idx: int) -> Dict:  # type: ignore
        return self.validation_step(batch, batch_idx)

    # ========== ON EPOCH END ==========

    def _general_epoch_end(self, outputs: List[Dict], group: str):
        with torch.no_grad():
            logs = {f"{group}/loss": torch.stack([out["loss"] for out in outputs]).mean()}
            accumulated_conf_matrix = torch.zeros(
                self.num_classes, self.num_classes, requires_grad=False, device=self.device
            )
            for out in outputs:
                _conf_matrix = out["confusion_matrix"]
                max_class_index, _ = _conf_matrix.shape
                accumulated_conf_matrix[:max_class_index, :max_class_index] += _conf_matrix
            logs[f"{group}/accuracy"] = accumulated_conf_matrix.trace() / accumulated_conf_matrix.sum()
            self.log_dict(logs)

    def training_epoch_end(self, outputs: List[Dict]):
        self._general_epoch_end(outputs, "train")

    def validation_epoch_end(self, outputs: List[Dict]):
        self._general_epoch_end(outputs, "val")

    def test_epoch_end(self, outputs: List[Dict]):
        self._general_epoch_end(outputs, "test")
