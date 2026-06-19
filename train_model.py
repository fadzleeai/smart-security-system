"""
train_model.py — extract 128-D embeddings from known_faces/ and train the
softmax classifier.  Run from the project root after registering faces:

    python train_model.py

Produces four pickle files in models/:
    embedding_classifier.pkl
    label_encoder.pkl
    class_centroids.pkl
    training_metadata.pkl

After training, restart main.py (or call engine.load_model()) so it picks up
the new model.
"""

import os
import sys
from collections import Counter
from datetime import datetime, timezone

import face_recognition
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.embedding_engine import (
    RegularizedSoftmaxClassifier,
    SimpleLabelEncoder,
    model_paths,
    save_pickle,
)


KNOWN_FACES_DIR      = os.path.join(BASE_DIR, "known_faces")
MODELS_DIR           = os.path.join(BASE_DIR, "models")
IMAGE_EXTENSIONS     = (".jpg", ".jpeg", ".png")
EMBEDDING_DIMENSIONS = 128
NUM_JITTERS          = 1
PROBABILITY_THRESHOLD      = 0.95
MIN_CENTROID_THRESHOLD     = 0.48
MAX_CENTROID_THRESHOLD     = 0.58
CENTROID_MARGIN            = 0.08


def person_name_from_filename(filename):
    stem = os.path.splitext(os.path.basename(filename))[0]
    base, separator, suffix = stem.rpartition("_")
    if separator and base and suffix.isdigit():
        return base
    return stem


def largest_face_location(locations):
    return max(
        locations,
        key=lambda loc: (loc[2] - loc[0]) * (loc[1] - loc[3]),
    )


def extract_embedding(image_path):
    try:
        image = face_recognition.load_image_file(image_path)
    except (OSError, ValueError) as error:
        return None, "UNREADABLE_IMAGE: {}".format(error)

    locations = face_recognition.face_locations(
        image, number_of_times_to_upsample=1, model="hog",
    )
    if not locations:
        return None, "NO_FACE"

    location  = largest_face_location(locations)
    encodings = face_recognition.face_encodings(
        image,
        known_face_locations=[location],
        num_jitters=NUM_JITTERS,
        model="small",
    )
    if not encodings:
        return None, "NO_EMBEDDING"

    note = "OK" if len(locations) == 1 else "LARGEST_OF_MULTIPLE"
    return np.asarray(encodings[0], dtype=np.float64), note


def calculate_centroids(features, names):
    centroids = {}
    for name in sorted(set(names), key=str.casefold):
        class_features = features[np.asarray([item == name for item in names])]
        centroids[name] = np.mean(class_features, axis=0)
    return centroids


def calculate_centroid_threshold(features, names, centroids):
    own_distances = [
        float(np.linalg.norm(feature - centroids[name]))
        for feature, name in zip(features, names)
    ]
    threshold = max(own_distances) + CENTROID_MARGIN
    threshold = float(np.clip(threshold, MIN_CENTROID_THRESHOLD, MAX_CENTROID_THRESHOLD))
    return threshold, own_distances


def remove_legacy_models():
    legacy_filenames = ("lbph_face_model.yml", "label_map.pkl")
    for filename in legacy_filenames:
        path = os.path.join(MODELS_DIR, filename)
        if os.path.isfile(path):
            try:
                os.remove(path)
                print("Removed legacy LBPH artifact:", path)
            except OSError as error:
                print("Warning: could not remove {}: {}".format(path, error))


def main():
    os.makedirs(KNOWN_FACES_DIR, exist_ok=True)
    os.makedirs(MODELS_DIR, exist_ok=True)

    image_files = [
        os.path.join(KNOWN_FACES_DIR, filename)
        for filename in sorted(os.listdir(KNOWN_FACES_DIR), key=str.casefold)
        if filename.lower().endswith(IMAGE_EXTENSIONS)
    ]

    embeddings     = []
    names          = []
    sample_counts  = Counter()
    skipped_counts = Counter()

    for image_path in image_files:
        embedding, note = extract_embedding(image_path)
        filename = os.path.basename(image_path)
        if embedding is None:
            skipped_counts[note.split(":", 1)[0]] += 1
            print("Skipped:", filename, "({})".format(note))
            continue

        person_name = person_name_from_filename(filename)
        embeddings.append(embedding)
        names.append(person_name)
        sample_counts[person_name] += 1
        print("Loaded:", filename, "->", person_name, "({})".format(note))

    print("\nTraining summary")
    print("================")
    print("Total training images:", len(image_files))
    print("Total usable 128D embeddings:", len(embeddings))
    print("Total authorized persons:", len(sample_counts))
    print("Samples per person:", dict(sorted(sample_counts.items())))
    if skipped_counts:
        print("Skipped samples:", dict(sorted(skipped_counts.items())))

    if len(embeddings) < 2:
        print("Not enough usable training images. Register more faces first.")
        return
    if len(sample_counts) < 2:
        print("At least two authorized people are required to train the classifier.")
        return

    features = np.asarray(embeddings, dtype=np.float64)
    if features.shape[1] != EMBEDDING_DIMENSIONS:
        print("Unexpected embedding dimensions:", features.shape[1])
        return

    label_encoder  = SimpleLabelEncoder().fit(names)
    encoded_labels = label_encoder.transform(names)
    classifier     = RegularizedSoftmaxClassifier().fit(features, encoded_labels)
    centroids      = calculate_centroids(features, names)
    centroid_threshold, own_distances = calculate_centroid_threshold(
        features, names, centroids,
    )

    predicted_labels        = classifier.predict(features)
    training_accuracy       = float(np.mean(predicted_labels == encoded_labels))
    training_probabilities  = classifier.predict_proba(features)
    predicted_columns       = np.argmax(training_probabilities, axis=1)
    winning_probabilities   = training_probabilities[
        np.arange(len(features)), predicted_columns,
    ]

    metadata = {
        "model_type":                  "RegularizedSoftmaxClassifier",
        "feature_extractor":           "face_recognition 128D face embedding",
        "embedding_dimensions":        EMBEDDING_DIMENSIONS,
        "num_jitters":                 NUM_JITTERS,
        "classes":                     [str(item) for item in label_encoder.classes_],
        "sample_counts":               dict(sorted(sample_counts.items())),
        "total_images":                len(image_files),
        "usable_samples":              len(features),
        "skipped_samples":             dict(sorted(skipped_counts.items())),
        "training_accuracy":           training_accuracy,
        "minimum_training_confidence": float(np.min(winning_probabilities)),
        "mean_training_confidence":    float(np.mean(winning_probabilities)),
        "maximum_own_centroid_distance": float(np.max(own_distances)),
        "probability_threshold":       PROBABILITY_THRESHOLD,
        "centroid_distance_threshold": centroid_threshold,
        "trained_at_utc":              datetime.now(timezone.utc).isoformat(),
    }

    paths = model_paths(MODELS_DIR)
    save_pickle(paths["classifier"],    classifier)
    save_pickle(paths["label_encoder"], label_encoder)
    save_pickle(paths["centroids"],     centroids)
    save_pickle(paths["metadata"],      metadata)
    remove_legacy_models()

    print("\nModel training complete")
    print("=======================")
    print("Classifier:",     paths["classifier"])
    print("Label encoder:",  paths["label_encoder"])
    print("Class centroids:", paths["centroids"])
    print("Training metadata:", paths["metadata"])
    print("Training accuracy: {:.2%}".format(training_accuracy))
    print(
        "Unknown rejection: confidence >= {:.0%} and distance <= {:.4f}".format(
            PROBABILITY_THRESHOLD, centroid_threshold,
        )
    )


if __name__ == "__main__":
    main()