import warnings

from sqlalchemy.exc import LegacyAPIWarning


def test_admin_routes_do_not_emit_sqlalchemy_legacy_get_warning(
        auth_client, sample_activity):
    with warnings.catch_warnings():
        warnings.simplefilter('error', LegacyAPIWarning)
        response = auth_client.get(f'/admin/activity/{sample_activity.id}')

    assert response.status_code == 200
