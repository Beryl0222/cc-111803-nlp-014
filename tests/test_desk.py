from pathlib import Path

from nlp_shipping_exception_resolution.desk_cli import load_case


def test_found_original_and_in_transit_replacement_require_followup():
    fixture = Path(__file__).parents[1] / 'fixtures'
    output = load_case(fixture / 'work.json', fixture / 'business.json')
    assert output['whole_order_delivered']
    assert output['pending'] == []
    assert output['actions'] == [{'id': 'RESHIP-4', 'next': '协调在途件'}]
