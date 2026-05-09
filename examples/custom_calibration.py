# /// script
# requires-python = ">=3.10"
# dependencies = ["groundlens"]
# ///
"""Custom DGI calibration with domain-specific pairs.

Demonstrates the full calibration workflow:
1. Provide verified (question, response) pairs from your domain.
2. Compute the DGI reference direction via ``calibrate()``.
3. Save calibration to JSON for reproducibility.
4. Use the calibrated DGI class for scoring.
"""

from groundlens import calibrate
from groundlens.dgi import DGI

# Step 1: Collect verified grounded pairs from your domain.
# In practice, use 20-100 pairs for best results.
medical_pairs = [
    ("What is hypertension?", "Hypertension is persistently elevated arterial blood pressure."),
    ("What causes type 2 diabetes?", "Type 2 diabetes is caused by insulin resistance."),
    ("What is an MRI?", "MRI uses magnetic fields and radio waves to create body images."),
    ("What are statins?", "Statins are drugs that lower cholesterol by inhibiting HMG-CoA."),
    ("What is anemia?", "Anemia is a condition with insufficient healthy red blood cells."),
    ("What is tachycardia?", "Tachycardia is a heart rate exceeding 100 beats per minute."),
    ("What is sepsis?", "Sepsis is a life-threatening organ dysfunction caused by infection."),
    ("What is a CT scan?", "CT scan uses X-rays to create cross-sectional body images."),
    ("What is asthma?", "Asthma is a chronic disease causing airway inflammation and narrowing."),
    ("What is dialysis?", "Dialysis filters waste from blood when kidneys cannot function."),
]

if __name__ == "__main__":
    print("=== Custom DGI Calibration ===\n")

    # Step 2: Compute the reference direction.
    result = calibrate(
        pairs=medical_pairs,
        metadata={"domain": "medical", "source": "manual_review"},
    )
    print("Calibration complete:")
    print(f"  Pairs:         {result.n_pairs}")
    print(f"  Embedding dim: {result.embedding_dim}")
    print(f"  Concentration: {result.concentration:.2f}")

    # Step 3: Save calibration for reproducibility.
    result.save("medical_calibration.json")
    print("  Saved to:      medical_calibration.json\n")

    # Step 4: Use the calibrated DGI scorer.
    dgi = DGI()
    dgi.calibrate(pairs=medical_pairs)

    test_cases = [
        ("What is pneumonia?", "Pneumonia is a lung infection causing inflammation of air sacs."),
        ("What is pneumonia?", "Pneumonia was discovered by Alexander Fleming in 1928."),
    ]

    print("Scoring with calibrated DGI:\n")
    for question, response in test_cases:
        score = dgi.score(question=question, response=response)
        status = "FLAGGED" if score.flagged else "PASS"
        print(f"  [{status:>7}] DGI={score.value:+.3f}  {response[:60]}...")
