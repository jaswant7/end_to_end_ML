import itertools
import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple, Sequence

import nltk
import numpy as np
import pandas as pd
import torch
from nltk.corpus import stopwords
from nltk.stem import PorterStemmer
from skmultilearn.model_selection import IterativeStratification

from tagifai import config, utils

# NLTK
nltk.download("stopwords")
STOPWORDS = stopwords.words("english")
porter = PorterStemmer()


# def load(shuffle: bool, num_samples: int = 0) -> pd.DataFrame:
#     """Load the data from local drive to a Pandas DataFrame.

#     Args:
#         shuffle (bool): Shuffle the data.
#         num_samples (int, optional): Number of samples to include (used for quick testting). Defaults to 0 which includes all samples.

#     Returns:
#         Dataframe, projects and tags dictionaries.
#     """
#     # Load data
#     projects_fp = Path(config.DATA_DIR, "projects.json")
#     tags_fp = Path(config.DATA_DIR, "tags.json")
#     projects_dict = utils.load_dict(filepath=projects_fp)
#     tags_dict = utils.load_dict(filepath=tags_fp)

#     # Create dataframe
#     df = pd.DataFrame(projects_dict)

#     # Shuffling since projects are chronologically organized
#     if shuffle:
#         df = df.sample(frac=1).reset_index(drop=True)

#     # Subset
#     if num_samples:
#         df = df[:num_samples]

#     return df, projects_dict, tags_dict


def filter_items(items: List, include: List = [], exclude: List = []) -> List:
    """Filter a list using inclusion and exclusion lists of items.

    Args:
        items (List): List of items to apply filters.
        include (List, optional): List of items to include. Defaults to [].
        exclude (List, optional): List of items to filter out. Defaults to [].

    Returns:
        Filtered list of items.
    """
    filtered = [
        item for item in items if item in include and item not in exclude
    ]
    return filtered


def clean(
    df: pd.DataFrame, include: List = [], exclude: List = [], min_tag_freq: int = 30
) -> Tuple:
    """Cleaning the raw data.

    Args:
        df (pd.DataFrame): Pandas DataFrame with data.
        include (List): list of tags to include.
        exclude (List): list of tags to exclude.
        min_tag_freq (int, optional): Minimum frequency of tags required. Defaults to 30.

    Returns:
        A cleaned dataframe and dictionary of tags and counts above the frequency threshold.
    """
    # Combine features
    df["text"] = df.title + " " + df.description

    # Filter tags for each project
    df.tags = df.tags.apply(filter_items, include=include, exclude=exclude)
    tags = Counter(itertools.chain.from_iterable(df.tags.values))

    # Filter tags that have fewer than `min_tag_freq` occurrences
    tags_above_freq = Counter(tag for tag in tags.elements() if tags[tag] >= min_tag_freq)
    df.tags = df.tags.apply(filter_items, include=list(tags_above_freq.keys()))

    # Remove projects with no more remaining relevant tags
    df = df[df.tags.map(len) > 0]

    return df, tags_above_freq

class Stemmer(PorterStemmer):
    def stem(self, word):

        if self.mode == self.NLTK_EXTENSIONS and word in self.pool:  # pragma: no cover, nltk
            return self.pool[word]

        if self.mode != self.ORIGINAL_ALGORITHM and len(word) <= 2:  # pragma: no cover, nltk
            # With this line, strings of length 1 or 2 don't go through
            # the stemming process, although no mention is made of this
            # in the published algorithm.
            return word

        stem = self._step1a(word)
        stem = self._step1b(stem)
        stem = self._step1c(stem)
        stem = self._step2(stem)
        stem = self._step3(stem)
        stem = self._step4(stem)
        stem = self._step5a(stem)
        stem = self._step5b(stem)

        return stem

def preprocess(
    text: str,
    lower: bool = True,
    stem: bool = False,
    filters: str = r"[!\"'#$%&()*\+,-./:;<=>?@\\\[\]^_`{|}~]",
    stopwords: List = STOPWORDS,
) -> str:
    """Conditional preprocessing on text.

    Args:
        text (str): String to preprocess.
        lower (bool, optional): Lower the text. Defaults to True.
        stem (bool, optional): Stem the text. Defaults to False.
        filters (str, optional): Filters to apply on text.
        stopwords (List, optional): List of words to filter out. Defaults to STOPWORDS.

    Returns:
        Preprocessed string.
    """
    # Lower
    if lower:
        text = text.lower()

    # Remove stopwords
    pattern = re.compile(r"\b(" + r"|".join(stopwords) + r")\b\s*")
    text = pattern.sub("", text)

    # Spacing and filters
    text = re.sub(r"([-;;.,!?<=>])", r" \1 ", text)
    text = re.sub(filters, r"", text)
    text = re.sub("[^A-Za-z0-9]+", " ", text)  # remove non alphanumeric chars
    text = re.sub(" +", " ", text)  # remove multiple spaces
    text = text.strip()

    # Remove links
    text = re.sub(r"http\S+", "", text)

    # Stemming
    if stem:
        stemmer = Stemmer()
        text = " ".join([stemmer.stem(word) for word in text.split(" ")])
        # text = " ".join([porter.stem(word) for word in text.split(" ")])

    return text


class LabelEncoder(object):
    """Encode labels into unique indices.

    Usage:

    ```python
    # Encode labels
    label_encoder = LabelEncoder()
    label_encoder.fit(labels)
    y = label_encoder.encode(labels)
    ```

    """

    def __init__(self, class_to_index: dict = {}):
        self.class_to_index = class_to_index or {}  # mutable defaults ;)
        self.index_to_class = {v: k for k, v in self.class_to_index.items()}
        self.classes = list(self.class_to_index.keys())

    def __len__(self):
        return len(self.class_to_index)

    def save(self, fp: str):
        with open(fp, "w") as fp:
            contents = {"class_to_index": self.class_to_index}
            json.dump(contents, fp, indent=4, sort_keys=False)

    @classmethod
    def load(cls, fp: str):
        with open(fp, "r") as fp:
            kwargs = json.load(fp=fp)
        return cls(**kwargs)


class MultiClassLabelEncoder(LabelEncoder):
    """Encode labels into unique indices
    for multi-class classification.
    """

    def __str__(self):
        return f"<MultiClassLabelEncoder(num_classes={len(self)})>"

    def fit(self, y: Sequence):
        """Learn label mappings from a series of class labels.

        Args:
            y (Sequence): Collection of labels as a pandas Series object.
        """
        classes = np.unique(y)
        for i, class_ in enumerate(classes):
            self.class_to_index[class_] = i
        self.index_to_class = {v: k for k, v in self.class_to_index.items()}
        self.classes = list(self.class_to_index.keys())
        return self

    def encode(self, y: pd.Series) -> np.ndarray:
        """Encode a collection of classes.

        Args:
            y (pd.Series): Collection of labels as a pandas Series object.

        Returns:
            Labels as (multilabel) one-hot encodings
        """
        encoded = np.zeros((len(y)), dtype=int)
        for i, item in enumerate(y):
            encoded[i] = self.class_to_index[item]
        return encoded

    def decode(self, y: np.ndarray) -> List[List[str]]:
        """Decode a collection of class indices.

        Args:
            y (np.ndarray): Labels as (multilabel) one-hot encodings

        Returns:
            List of original labels for each output.
        """
        classes = []
        for i, item in enumerate(y):
            classes.append(self.index_to_class[item])
        return classes


class MultiLabelLabelEncoder(LabelEncoder):
    """Encode labels into unique indices
    for multi-label classification.
    """

    def __str__(self):
        return f"<MultiLabelLabelEncoder(num_classes={len(self)})>"

    def fit(self, y: Sequence):
        """Learn label mappings from a series of class labels.

        Args:
            y (Sequence): Collection of labels as a pandas Series object.
        """
        classes = np.unique(list(itertools.chain.from_iterable(y)))
        for i, class_ in enumerate(classes):
            self.class_to_index[class_] = i
        self.index_to_class = {v: k for k, v in self.class_to_index.items()}
        self.classes = list(self.class_to_index.keys())
        return self

    def encode(self, y: pd.Series) -> np.ndarray:
        """Encode a collection of labels using (multilabel) one-hot encoding.

        Args:
            y (pd.Series): Collection of labels as a pandas Series object.

        Returns:
            Labels as (multilabel) one-hot encodings
        """
        y_one_hot = np.zeros((len(y), len(self.class_to_index)), dtype=int)
        for i, item in enumerate(y):
            for class_ in item:
                y_one_hot[i][self.class_to_index[class_]] = 1
        return y_one_hot

    def decode(self, y: np.ndarray) -> List[List[str]]:
        """Decode a (multilabel) one-hot encoding into corresponding labels.

        Args:
            y (np.ndarray): Labels as (multilabel) one-hot encodings

        Returns:
            List of original labels for each output.
        """
        classes = []
        for i, item in enumerate(y):
            indices = np.where(np.asarray(item) == 1)[0]
            classes.append([self.index_to_class[index] for index in indices])
        return classes



def iterative_train_test_split(
    X: pd.Series, y: np.ndarray, train_size: float = 0.7
) -> Tuple:
    """Custom iterative train test split which
    'maintains balanced representation with respect
    to order-th label combinations.'

    Args:
        X (pd.Series): Input features as a pandas Series object.
        y (np.ndarray): One-hot encoded labels.
        train_size (float, optional): Proportion of data for first split. Defaults to 0.7.

    Returns:
        Two stratified splits based on specified proportions.
    """
    stratifier = IterativeStratification(
        n_splits=2,
        order=1,
        sample_distribution_per_fold=[
            1.0 - train_size,
            train_size,
        ],
    )
    train_indices, test_indices = next(stratifier.split(X, y))
    X_train, y_train = X[train_indices], y[train_indices]
    X_test, y_test = X[test_indices], y[test_indices]
    return X_train, X_test, y_train, y_test


# def split(X: pd.Series, y: np.ndarray, train_size: float = 0.7) -> Tuple:
#     """Split data into three (train, val, test) splits.

#     Args:
#         X (pd.Series): input features as a pandas Series object.
#         y (np.ndarray): one-hot encoded labels.
#         train_size (float, optional): proportion of data for train split. Defaults to 0.7.

#     Returns:
#         Inputs and outputs of the three splits (respectively).
#     """
#     X_train, X_, y_train, y_ = iterative_train_test_split(
#         X, y, train_size=train_size
#     )
#     X_val, X_test, y_val, y_test = iterative_train_test_split(
#         X_, y_, train_size=0.5
#     )
#     return X_train, X_val, X_test, y_train, y_val, y_test


class Tokenizer(object):
    def __init__(
        self,
        char_level: bool,
        num_tokens: int = None,
        pad_token: str = "<PAD>",
        oov_token: str = "<UNK>",
        token_to_index: dict = None,
    ):
        self.char_level = char_level
        self.separator = "" if self.char_level else " "
        if num_tokens:
            num_tokens -= 2  # pad + unk tokens
        self.num_tokens = num_tokens
        self.oov_token = oov_token
        if not token_to_index:
            token_to_index = {"<PAD>": 0, "<UNK>": 1}
        self.token_to_index = token_to_index
        self.index_to_token = {v: k for k, v in self.token_to_index.items()}

    def __len__(self):
        return len(self.token_to_index)

    def __str__(self):
        return f"<Tokenizer(num_tokens={len(self)})>"

    def fit_on_texts(self, texts: List):
        """Learn token mappings from a list of texts.

        Args:
            texts (List): List of texts made of tokens.
        """
        if self.char_level:
            all_tokens = [token for text in texts for token in text]
        if not self.char_level:
            all_tokens = [token for text in texts for token in text.split(" ")]
        counts = Counter(all_tokens).most_common(self.num_tokens)
        self.min_token_freq = counts[-1][1]
        for token, count in counts:
            index = len(self)
            self.token_to_index[token] = index
            self.index_to_token[index] = token
        return self

    def texts_to_sequences(self, texts: List) -> List[np.ndarray]:
        """Convert a list of texts to a lists of arrays of indices.

        Args:
            texts (List): List of texts to tokenize and map to indices.

        Returns:
            A list of mapped tokens.
        """
        sequences = []
        for text in texts:
            if not self.char_level:
                text = text.split(" ")
            sequence = []
            for token in text:
                sequence.append(
                    self.token_to_index.get(
                        token, self.token_to_index[self.oov_token]
                    )
                )
            sequences.append(np.asarray(sequence))
        return sequences

    def sequences_to_texts(self, sequences: List) -> List:
        """Convert a lists of arrays of indices to a list of texts.

        Args:
            sequences (List): list of mapped tokens to convert back to text.

        Returns:
            Mapped text from index tokens.
        """
        texts = []
        for sequence in sequences:
            text = []
            for index in sequence:
                text.append(self.index_to_token.get(index, self.oov_token))
            texts.append(self.separator.join([token for token in text]))
        return texts

    def save(self, fp: str):
        with open(fp, "w") as fp:
            contents = {
                "char_level": self.char_level,
                "oov_token": self.oov_token,
                "token_to_index": self.token_to_index,
            }
            json.dump(contents, fp, indent=4, sort_keys=False)

    @classmethod
    def load(cls, fp: str):
        with open(fp, "r") as fp:
            kwargs = json.load(fp=fp)
        return cls(**kwargs)


# def tokenize_text(
#     X: np.ndarray, char_level: bool, tokenizer: Tokenizer = None
# ) -> Tuple:
#     """Tokenize an array containining text.

#     Args:
#         X (np.ndarray): Arrays containing the data to tokenize.
#         char_level (bool): Whether to tokenize at character level.
#         tokenizer (Tokenizer): Tokenizer to use for tokenization. Defaults to None.

#     Returns:
#         Tokenized inputs and tokenizer.
#     """
#     # Tokenize inputs
#     if not tokenizer:
#         tokenizer = Tokenizer(char_level=char_level)
#         tokenizer.fit_on_texts(texts=X)
#     X = np.array(tokenizer.texts_to_sequences(X))
#     return X, tokenizer


def pad_sequences(sequences: np.ndarray, max_seq_len: int = 0):
    """Pad sequences to max length in sequence.

    Args:
        sequences (np.ndarray): Collection of sequences to pad.
        max_seq_len (int, optional): Length to pad sequences to. Defaults to 0.
    """
    max_seq_len = max(
        max_seq_len, max(len(sequence) for sequence in sequences)
    )
    padded_sequences = np.zeros((len(sequences), max_seq_len))
    for i, sequence in enumerate(sequences):
        padded_sequences[i][: len(sequence)] = sequence
    return padded_sequences


class CNNTextDataset(torch.utils.data.Dataset):
    def __init__(self, X, y, max_filter_size):
        self.X = X
        self.y = y
        self.max_filter_size = max_filter_size

    def __len__(self):
        return len(self.y)

    def __str__(self):
        return f"<Dataset(N={len(self)})>"

    def __getitem__(self, index: int) -> List:
        X = self.X[index]
        y = self.y[index]
        return [X, y]

    def collate_fn(self, batch: List) -> Tuple:
        """Processing on a batch.

        Args:
            batch (List): List of inputs and outputs.

        Returns:
            Processed inputs and outputs.
        """
        # Get inputs
        X = np.array(batch, dtype=object)[:, 0]
        y = np.stack(np.array(batch, dtype=object)[:, 1], axis=0)

        # Pad inputs
        X = pad_sequences(sequences=X, max_seq_len=self.max_filter_size)

        # Cast
        X = torch.LongTensor(X.astype(np.int32))
        y = torch.FloatTensor(y.astype(np.int32))

        return X, y

    def create_dataloader(
        self, batch_size: int, shuffle: bool = False, drop_last: bool = False
    ):
        """Create dataloaders to load batches with.

        Args:
            batch_size (int): Number of samples per batch.
            shuffle (bool, optional): Shuffle each batch. Defaults to False.
            drop_last (bool, optional): Drop the last batch if it's less than `batch_size`. Defaults to False.

        Returns:
            Torch dataloader to load batches with.
        """
        return torch.utils.data.DataLoader(
            dataset=self,
            batch_size=batch_size,
            collate_fn=self.collate_fn,
            shuffle=shuffle,
            drop_last=drop_last,
            pin_memory=True,
        )


# def get_dataloader(
#     data: Tuple, max_filter_size: int, batch_size: int
# ) -> Tuple:
#     """Create dataloader from data.

#     Args:
#         data (Tuple): [description]
#         max_filter_size (int): [description]
#         batch_size (int): [description]

#     Returns:
#         Created dataloader with data.
#     """
#     # Create dataset
#     X, y = data
#     dataset = CNNTextDataset(X=X, y=y, max_filter_size=max_filter_size)

#     # Create dataloaders
#     dataloader = dataset.create_dataloader(batch_size=batch_size)

#     return dataloader


# if __name__ == "__main__":
#     pass