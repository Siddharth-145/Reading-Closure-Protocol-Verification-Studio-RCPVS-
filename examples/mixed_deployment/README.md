# mixed_deployment
Each implementation family passes in isolation (common-mode profiles ordered/ordered and unordered/unordered are safe) but the mixed deployment fails: one endpoint waits for an acknowledgement the other never sends.

_Synthetic fixture: an engineered test case for the mechanism above, not evidence from real protocols._
