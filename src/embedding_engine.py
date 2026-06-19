import os
import pickle

import numpy as np


MODEL_FILENAMES = {
    "classifier": "embedding_classifier.pkl",
    "label_encoder": "label_encoder.pkl",
    "centroids": "class_centroids.pkl",
    "metadata": "training_metadata.pkl",
}


class SimpleLabelEncoder:
    """Small pickle-friendly replacement for sklearn's label encoder."""

    def fit(self, labels):
        unique_labels = sorted({str(label) for label in labels}, key=str.casefold)
        if not unique_labels:
            raise ValueError("At least one label is required.")
        self.classes_ = np.asarray(unique_labels, dtype=object)
        return self

    def transform(self, labels):
        class_to_index = {
            str(label): index for index, label in enumerate(self.classes_)
        }
        try:
            return np.asarray(
                [class_to_index[str(label)] for label in labels],
                dtype=np.int64,
            )
        except KeyError as error:
            raise ValueError("Unknown label: {}".format(error.args[0])) from error

    def inverse_transform(self, label_ids):
        labels = []
        for label_id in label_ids:
            index = int(label_id)
            if index < 0 or index >= len(self.classes_):
                raise ValueError("Label index is out of range: {}".format(index))
            labels.append(str(self.classes_[index]))
        return np.asarray(labels, dtype=object)


class RegularizedSoftmaxClassifier:
    """Class-balanced linear softmax classifier trained with NumPy."""

    def __init__(
        self,
        learning_rate=0.08,
        epochs=1600,
        l2_strength=0.02,
    ):
        self.learning_rate = float(learning_rate)
        self.epochs = int(epochs)
        self.l2_strength = float(l2_strength)

    @staticmethod
    def _validate_features(features):
        values = np.asarray(features, dtype=np.float64)
        if values.ndim != 2:
            raise ValueError("Features must be a two-dimensional array.")
        if values.shape[0] == 0:
            raise ValueError("At least one training sample is required.")
        if not np.all(np.isfinite(values)):
            raise ValueError("Features contain non-finite values.")
        return values

    @staticmethod
    def _softmax(logits):
        shifted = logits - np.max(logits, axis=1, keepdims=True)
        exponentials = np.exp(shifted)
        return exponentials / np.sum(
            exponentials,
            axis=1,
            keepdims=True,
        )

    def fit(self, features, labels):
        features = self._validate_features(features)
        labels = np.asarray(labels, dtype=np.int64)
        if labels.ndim != 1 or len(labels) != len(features):
            raise ValueError("Labels must contain one value per sample.")

        self.classes_ = np.unique(labels)
        self.feature_mean_ = np.mean(features, axis=0)
        self.feature_scale_ = np.std(features, axis=0)
        self.feature_scale_[self.feature_scale_ < 1e-6] = 1.0

        normalized = (features - self.feature_mean_) / self.feature_scale_
        sample_count, feature_count = normalized.shape
        class_count = len(self.classes_)
        self.coef_ = np.zeros(
            (feature_count, class_count),
            dtype=np.float64,
        )
        self.intercept_ = np.zeros(class_count, dtype=np.float64)

        class_to_column = {
            int(label): index for index, label in enumerate(self.classes_)
        }
        columns = np.asarray(
            [class_to_column[int(label)] for label in labels],
            dtype=np.int64,
        )
        targets = np.eye(class_count, dtype=np.float64)[columns]

        counts = np.bincount(columns, minlength=class_count).astype(np.float64)
        class_weights = sample_count / (class_count * counts)
        sample_weights = class_weights[columns]
        weight_total = float(np.sum(sample_weights))

        if class_count > 1:
            for _ in range(self.epochs):
                probabilities = self._softmax(
                    normalized @ self.coef_ + self.intercept_
                )
                errors = (
                    probabilities - targets
                ) * sample_weights[:, np.newaxis]
                gradient_weights = (
                    normalized.T @ errors / weight_total
                    + self.l2_strength * self.coef_
                )
                gradient_bias = np.sum(errors, axis=0) / weight_total
                self.coef_ -= self.learning_rate * gradient_weights
                self.intercept_ -= self.learning_rate * gradient_bias

        return self

    def predict_proba(self, features):
        features = self._validate_features(features)
        normalized = (
            features - self.feature_mean_
        ) / self.feature_scale_
        if len(self.classes_) == 1:
            return np.ones((len(features), 1), dtype=np.float64)
        return self._softmax(
            normalized @ self.coef_ + self.intercept_
        )

    def predict(self, features):
        probabilities = self.predict_proba(features)
        columns = np.argmax(probabilities, axis=1)
        return self.classes_[columns]


def model_paths(models_dir):
    return {
        key: os.path.join(models_dir, filename)
        for key, filename in MODEL_FILENAMES.items()
    }


def save_pickle(path, value):
    with open(path, "wb") as output_file:
        pickle.dump(value, output_file, protocol=pickle.HIGHEST_PROTOCOL)


def load_model_bundle(models_dir):
    paths = model_paths(models_dir)
    missing = [
        path for path in paths.values() if not os.path.isfile(path)
    ]
    if missing:
        raise FileNotFoundError(
            "Missing trained model files: {}".format(
                ", ".join(os.path.basename(path) for path in missing)
            )
        )

    with open(paths["classifier"], "rb") as model_file:
        classifier = pickle.load(model_file)
    with open(paths["label_encoder"], "rb") as label_file:
        label_encoder = pickle.load(label_file)
    with open(paths["centroids"], "rb") as centroid_file:
        centroids = pickle.load(centroid_file)
    with open(paths["metadata"], "rb") as metadata_file:
        metadata = pickle.load(metadata_file)

    if not hasattr(classifier, "predict_proba"):
        raise ValueError("The classifier model is invalid.")
    if not hasattr(label_encoder, "inverse_transform"):
        raise ValueError("The label encoder is invalid.")
    if not isinstance(centroids, dict) or not centroids:
        raise ValueError("The class centroid file is invalid.")
    if not isinstance(metadata, dict):
        raise ValueError("The training metadata file is invalid.")

    for key in ("probability_threshold", "centroid_distance_threshold"):
        if key not in metadata:
            raise ValueError(
                "Training metadata is missing {}.".format(key)
            )

    return {
        "classifier": classifier,
        "label_encoder": label_encoder,
        "centroids": centroids,
        "metadata": metadata,
        "paths": paths,
    }


def predict_embedding(embedding, model_bundle):
    feature = np.asarray(embedding, dtype=np.float64).reshape(1, -1)
    classifier = model_bundle["classifier"]
    label_encoder = model_bundle["label_encoder"]
    centroids = model_bundle["centroids"]
    metadata = model_bundle["metadata"]

    probabilities = classifier.predict_proba(feature)[0]
    probability_column = int(np.argmax(probabilities))
    encoded_label = int(classifier.classes_[probability_column])
    candidate_name = str(
        label_encoder.inverse_transform([encoded_label])[0]
    )
    confidence = float(probabilities[probability_column])

    if candidate_name not in centroids:
        raise ValueError(
            "No centroid was saved for class {}.".format(candidate_name)
        )
    centroid = np.asarray(centroids[candidate_name], dtype=np.float64)
    centroid_distance = float(
        np.linalg.norm(feature[0] - centroid)
    )

    probability_threshold = float(metadata["probability_threshold"])
    centroid_threshold = float(
        metadata["centroid_distance_threshold"]
    )
    accepted = (
        confidence >= probability_threshold
        and centroid_distance <= centroid_threshold
    )

    return {
        "name": candidate_name if accepted else "Unknown",
        "candidate_name": candidate_name,
        "confidence": confidence,
        "centroid_distance": centroid_distance,
        "accepted": accepted,
    }