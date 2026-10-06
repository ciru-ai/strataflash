from calculator import apply_discount

def test_apply_discount_percentage():
    assert apply_discount(100, 0.15) == 85.0
