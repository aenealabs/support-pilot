from support_pilot.auth import AuthSettings, user_from_claims

SETTINGS = AuthSettings("oidc", approver_emails=frozenset({"lead@example.com"}))


def test_only_the_approver_role_or_allow_list_makes_an_approver():
    claims = {"sub": "1", "name": "Sam", "email": "sam@example.com"}
    assert user_from_claims(claims | {"roles": ["SupportPilot.Approver"]}, SETTINGS).approver
    assert not user_from_claims(claims | {"roles": ["SupportPilot.TradeCompliance"]},
                                SETTINGS).approver  # a role copied from PLM Insight, removed
    assert user_from_claims(claims | {"email": "LEAD@example.com"}, SETTINGS).approver
