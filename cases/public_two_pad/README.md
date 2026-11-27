# Public case: two-pad shared compressor

Open demonstration case for FieldVET. Inventories and prices are synthetic;
they do not contain operator confidential data.

## What it shows

Two pads share one compressor. Base capacity fits one pad’s peak gas but not
both. A facility project expands the compressor. Network-priced selection funds
both pads with the expansion when the expansion capital is economic.

## Reproduce

```bash
pip install -e ".[dev]"
fieldvet network --pads a,b
fieldvet network --pads a,b --expand
fieldvet optimize
fieldvet attribute
fieldvet tie-in
```

Hindcast CSV (`reported_production.csv`) is a synthetic “reported” series for
the fixed both-pads+expand plan, used by `landmark_fieldvet.hindcast`.

## License

This case directory is released under Apache-2.0 (see repo `LICENSE`).
