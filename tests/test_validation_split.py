from media_recon.generate import dev_hard, validation


def test_validation_vendors_disjoint_from_dev():
    dev = {v[0] for v in dev_hard.VENDORS} | {a for v in dev_hard.VENDORS for a in v[1]}
    val = {v[0] for v in validation.VENDORS} | {a for v in validation.VENDORS for a in v[1]}
    assert not dev & val
    assert not set(validation.VAL_SEEDS) & set(dev_hard.DEV_SEEDS)


def test_validation_generate_restores_dev_globals(tmp_path):
    before = dev_hard.VENDORS
    validation.generate(tmp_path / "v", seed=validation.VAL_SEEDS[0])
    assert dev_hard.VENDORS is before
