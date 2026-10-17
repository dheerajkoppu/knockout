![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

# Knockout label-agent

Knockout step 6. Checks each predicted effect against the drug's FDA label (boxed warning, warnings and
precautions, adverse reactions) and returns the matching sentence verbatim with its section. No model takes part.
Answers `unknown` with the reason when openFDA has no label or fails.

Called by knockout-orchestrator over the KnockoutSliceProtocol.
