from src.safety.checks import find_duplicate_ingredients, normalize_ingredient, split_ingredients


def item(brand, ingredient, status="active"):
    return {"id": 1, "brand_name": brand, "active_ingredient": ingredient, "status": status}


def test_simple_duplicate():
    groups = find_duplicate_ingredients([item("Panadol", "Paracetamol"), item("Calpol", "Paracetamol"),
                                         item("Zyrtec", "Cetirizine")])
    assert len(groups) == 1 and groups[0].ingredient == "paracetamol"
    assert sorted(groups[0].brands) == ["Calpol", "Panadol"]


def test_combination_products_share_single_ingredient():
    groups = find_duplicate_ingredients([item("Panadol Extra", "Paracetamol + Caffeine"),
                                         item("Panadol", "Paracetamol")])
    assert [g.ingredient for g in groups] == ["paracetamol"]


def test_salt_names_normalised():
    assert normalize_ingredient("Cetirizine HCl") == "cetirizine"
    assert normalize_ingredient("Diclofenac sodium (BP)") == "diclofenac"


def test_used_up_items_ignored():
    assert find_duplicate_ingredients([item("A", "Ibuprofen"), item("B", "Ibuprofen", "used_up")]) == []


def test_no_duplicates_and_empty():
    assert find_duplicate_ingredients([]) == []
    assert find_duplicate_ingredients([item("A", "Ibuprofen"), item("B", "Cetirizine")]) == []


def test_split_ingredients():
    assert split_ingredients("Ibuprofen + Pseudoephedrine") == ["ibuprofen", "pseudoephedrine"]


def test_multiple_groups_sorted():
    groups = find_duplicate_ingredients([item("A", "Ibuprofen"), item("B", "Ibuprofen"),
                                         item("C", "Aspirin"), item("D", "Aspirin")])
    assert [g.ingredient for g in groups] == ["aspirin", "ibuprofen"]
