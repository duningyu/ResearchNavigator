# OA root-cause attribution — blocked

The required frozen manifest is missing from the current checkout. The
historical manifest blob at `16211a4` matches the required SHA256, but using it
would change the audit input and would not prove that the current checkout is
the frozen manifest context.

No external diagnostic requests were issued. Case A and Case B attribution is
therefore unresolved, with LOW confidence. Frozen Core and the release ZIP
remain unchanged.

Next legal action: restore or provide the exact frozen manifest in the
authorized validation context, recompute the required SHA256, and only then
run the bounded same-input differential probes.
