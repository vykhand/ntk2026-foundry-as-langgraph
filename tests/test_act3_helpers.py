from scripts import act3


def test_traces_url_follows_the_portal_pattern():
    url = act3.traces_url(org="org", resource_group="rg", account="acc", project="proj", tenant="tid")
    assert url == "https://ai.azure.com/nextgen/r/org,rg,,acc,proj/build/agents/ntk-asistent/traces?tid=tid"


def test_the_portal_org_segment_is_the_subscription_id_base64url():
    # A made-up subscription id: the segment is its 16 bytes, base64url without padding.
    assert act3.portal_org("00000000-0000-0000-0000-000000000001") == "AAAAAAAAAAAAAAAAAAAAAQ"
    assert act3.portal_org("") == ""
    assert act3.portal_org("not-a-guid") == ""


def test_portal_links_use_the_azd_env():
    links = act3.portal_links(
        {
            "AZURE_RESOURCE_GROUP": "rg-x",
            "AZURE_AI_ACCOUNT_NAME": "cog-x",
            "AZURE_AI_PROJECT_NAME": "p",
            "AZURE_TENANT_ID": "t",
            "AZURE_SUBSCRIPTION_ID": "s",
        }
    )
    assert "rg-x,,cog-x,p" in links["traces"] and links["traces"].endswith("?tid=t")
    assert "/subscriptions/s/resourceGroups/rg-x/" in links["app_insights"]


def test_span_table_formats_rows_and_empty():
    assert "no spans" in act3.span_table([])
    rows = [
        {
            "timestamp": "2026-09-06T00:10:11.5Z",
            "itemType": "dependency",
            "name": "invoke_agent ntk",
            "duration": 1234.5,
            "op": "invoke_agent",
        },
        {
            "timestamp": "2026-09-06T00:10:12.5Z",
            "itemType": "request",
            "name": "POST /responses",
            "duration": None,
            "op": None,
        },
    ]
    table = act3.span_table(rows)
    assert "00:10:11" in table and "invoke_agent" in table and "1234" in table
    assert "POST /responses" in table and "-" in table
