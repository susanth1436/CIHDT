## Model registry

Trained detector versions are written to this directory by the pipeline as
`detector_vNNNN.joblib`, alongside a `ledger.json` recording which version is
active and which have been marked untrusted.

Nothing here is committed. The files are joblib pickles, which execute code
on load and so should never be distributed, and they are rebuilt from scratch
on any machine:

```bash
python cli.py --walk
```

Step 6 trains model v1, Step 11 trains and promotes a candidate as v2, and
Step 12 can roll back to the last version still trusted.
