from os.path import join
from unittest import TestCase

from hydra.experimental import initialize_config_dir, compose

from dataset import PathContextDataset, PathContextBatch
from model.modules import PathEncoder
from utils.filesystem import get_test_data_info, get_config_directory
from utils.vocabulary import Vocabulary, PAD


class TestPathEncoder(TestCase):
    def test_forward(self):
        with initialize_config_dir(config_dir=get_config_directory()):
            data_folder, dataset_name = get_test_data_info()
            config = compose("main", overrides=[f"data_folder={data_folder}", f"dataset.name={dataset_name}"])

        dataset_folder = join(config.data_folder, config.dataset.name)
        vocabulary = Vocabulary.load_vocabulary(join(dataset_folder, config.vocabulary_name))
        data_file_path = join(dataset_folder, f"{config.dataset.name}.{config.train_holdout}.c2s")
        dataset = PathContextDataset(data_file_path, config, vocabulary, False)
        batch = PathContextBatch([dataset[i] for i in range(config.hyper_parameters.batch_size)])

        model = PathEncoder(
            config.encoder,
            config.decoder.decoder_size,
            len(vocabulary.token_to_id),
            vocabulary.token_to_id[PAD],
            len(vocabulary.node_to_id),
            vocabulary.node_to_id[PAD],
        )
        output = model(batch.contexts)

        true_shape = (sum(batch.contexts_per_label), config.decoder.decoder_size)
        self.assertTupleEqual(true_shape, output.shape)
