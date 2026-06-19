"""
evaluate_engine.py — measure accuracy of the trained embedding classifier
against a held-out test set.

Directory structure expected:
    test_data/
        authorized/
            alice/   *.jpg / *.jpeg / *.png
            bob/     *.jpg …
        unknown/     *.jpg …

Run from the project root:
    python evaluate_engine.py

Writes a CSV report to evaluation_results.csv and prints a confusion matrix.
"""

import csv
import os
import pickle
import sys

import face_recognition

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.embedding_engine import load_model_bundle, predict_embedding


MODELS_DIR     = os.path.join(BASE_DIR, "models")
AUTHORIZED_DIR = os.path.join(BASE_DIR, "test_data", "authorized")
UNKNOWN_DIR    = os.path.join(BASE_DIR, "test_data", "unknown")
RESULTS_FILE   = os.path.join(BASE_DIR, "evaluation_results.csv")
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")


def load_embedding_models():
    try:
        model_bundle = load_model_bundle(MODELS_DIR)
    except (
        OSError, EOFError, pickle.PickleError, AttributeError, ValueError,
    ) as error:
        print("Embedding classifier could not be loaded:", error)
        print("Please run train_model.py first.")
        return None

    print("Loaded classifier:", model_bundle["paths"]["classifier"])
    return model_bundle


def image_files_in(folder):
    if not os.path.isdir(folder):
        return []
    return [
        os.path.join(folder, filename)
        for filename in sorted(os.listdir(folder), key=str.casefold)
        if (
            os.path.isfile(os.path.join(folder, filename))
            and filename.lower().endswith(IMAGE_EXTENSIONS)
        )
    ]


def collect_test_samples():
    samples = []

    if os.path.isdir(AUTHORIZED_DIR):
        for person_name in sorted(os.listdir(AUTHORIZED_DIR), key=str.casefold):
            person_folder = os.path.join(AUTHORIZED_DIR, person_name)
            if not os.path.isdir(person_folder):
                continue
            for image_path in image_files_in(person_folder):
                samples.append({
                    "path":          image_path,
                    "expected_type": "authorized",
                    "expected_name": person_name,
                })

    for image_path in image_files_in(UNKNOWN_DIR):
        samples.append({
            "path":          image_path,
            "expected_type": "unknown",
            "expected_name": "Unknown",
        })

    return samples


def largest_face_location(locations):
    return max(
        locations,
        key=lambda loc: (loc[2] - loc[0]) * (loc[1] - loc[3]),
    )


def evaluate_image(image_path, model_bundle):
    try:
        image = face_recognition.load_image_file(image_path)
    except (OSError, ValueError):
        return {
            "name": "Unknown", "candidate_name": "",
            "confidence": 0.0, "centroid_distance": float("inf"),
            "note": "UNREADABLE_IMAGE",
        }

    locations = face_recognition.face_locations(
        image, number_of_times_to_upsample=1, model="hog",
    )
    if not locations:
        return {
            "name": "Unknown", "candidate_name": "",
            "confidence": 0.0, "centroid_distance": float("inf"),
            "note": "NO_FACE",
        }

    location  = largest_face_location(locations)
    encodings = face_recognition.face_encodings(
        image,
        known_face_locations=[location],
        num_jitters=1,
        model="small",
    )
    if not encodings:
        return {
            "name": "Unknown", "candidate_name": "",
            "confidence": 0.0, "centroid_distance": float("inf"),
            "note": "NO_EMBEDDING",
        }

    prediction = predict_embedding(encodings[0], model_bundle)
    prediction["note"] = (
        "OK" if len(locations) == 1 else "LARGEST_OF_MULTIPLE"
    )
    return prediction


def safe_rate(numerator, denominator):
    return numerator / denominator if denominator else 0.0


def print_report(metrics, model_bundle):
    metadata = model_bundle["metadata"]
    print("\nEvaluation Results")
    print("==================")
    print("Total test images:", metrics["total"])
    print("Correct predictions:", metrics["correct"])
    print("Accuracy: {:.2%}".format(metrics["accuracy"]))
    print("False Positive:", metrics["false_positive"])
    print("False Negative:", metrics["false_negative"])
    print("False Positive Rate: {:.2%}".format(metrics["fpr"]))
    print("False Negative Rate: {:.2%}".format(metrics["fnr"]))
    print(
        "Thresholds: confidence >= {:.0%}, distance <= {:.4f}".format(
            metadata["probability_threshold"],
            metadata["centroid_distance_threshold"],
        )
    )
    print("\nConfusion Matrix")
    print("                         Predicted Authorized  Predicted Unknown")
    print(
        "Actual Authorized       {:>20}  {:>17}".format(
            metrics["true_positive"], metrics["false_negative"],
        )
    )
    print(
        "Actual Unknown          {:>20}  {:>17}".format(
            metrics["false_positive"], metrics["true_negative"],
        )
    )
    print("\nDetailed results saved to:", RESULTS_FILE)


def main():
    model_bundle = load_embedding_models()
    if model_bundle is None:
        return

    samples = collect_test_samples()
    if not samples:
        print("No test images found.")
        print(
            "Add images to test_data/authorized/person_name/ and test_data/unknown/."
        )
        return

    true_positive = true_negative = false_positive = false_negative = 0
    rows     = []
    metadata = model_bundle["metadata"]

    for sample in samples:
        prediction    = evaluate_image(sample["path"], model_bundle)
        predicted_name = prediction["name"]

        if sample["expected_type"] == "authorized":
            correct = predicted_name.casefold() == sample["expected_name"].casefold()
            if correct:
                true_positive += 1
                outcome = "TP"
            else:
                false_negative += 1
                outcome = "FN"
        else:
            correct = predicted_name == "Unknown"
            if correct:
                true_negative += 1
                outcome = "TN"
            else:
                false_positive += 1
                outcome = "FP"

        rows.append({
            "image_path":                  os.path.relpath(sample["path"], BASE_DIR),
            "expected_type":               sample["expected_type"],
            "expected_name":               sample["expected_name"],
            "predicted_name":              predicted_name,
            "candidate_name":              prediction.get("candidate_name", ""),
            "classifier_confidence":       "{:.4f}".format(prediction["confidence"]),
            "centroid_distance":           "{:.4f}".format(prediction["centroid_distance"]),
            "probability_threshold":       "{:.4f}".format(metadata["probability_threshold"]),
            "centroid_distance_threshold": "{:.4f}".format(metadata["centroid_distance_threshold"]),
            "correct":                     correct,
            "outcome":                     outcome,
            "note":                        prediction["note"],
        })

    fieldnames = [
        "image_path", "expected_type", "expected_name", "predicted_name",
        "candidate_name", "classifier_confidence", "centroid_distance",
        "probability_threshold", "centroid_distance_threshold",
        "correct", "outcome", "note",
    ]
    with open(RESULTS_FILE, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    total               = len(samples)
    correct_predictions = true_positive + true_negative
    authorized_total    = true_positive + false_negative
    unknown_total       = true_negative + false_positive
    metrics = {
        "total":          total,
        "correct":        correct_predictions,
        "accuracy":       safe_rate(correct_predictions, total),
        "true_positive":  true_positive,
        "true_negative":  true_negative,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "fpr":            safe_rate(false_positive, unknown_total),
        "fnr":            safe_rate(false_negative, authorized_total),
    }
    print_report(metrics, model_bundle)


if __name__ == "__main__":
    main()