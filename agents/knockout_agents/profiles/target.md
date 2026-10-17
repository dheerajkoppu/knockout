![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

# Knockout target-agent

Knockout steps 1 and 2. For a drug, returns its ChEMBL parent molecule, every protein target with the action
types ChEMBL records, and which way the drug pushes each protein (lowers, raises or unknown). Only human single
proteins are used. Answers `unknown` with the reason when ChEMBL or the Knockout API fails.

Called by knockout-orchestrator over the KnockoutSliceProtocol.
