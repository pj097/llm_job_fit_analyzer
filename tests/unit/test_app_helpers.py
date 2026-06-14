from app import clean_list, order_table_columns


def test_order_table_columns_priority_first_and_skips_missing():
    # engagement_type/salary absent -> skipped; order follows TABLE_PRIORITY_COLUMNS
    cols = ["company", "job_url", "overall_fit", "job_title"]
    assert order_table_columns(cols) == ["overall_fit", "job_title", "company", "job_url"]


def test_order_table_columns_appends_extras_after_priority():
    cols = ["overall_fit", "job_title", "company", "job_url", "location_match", "visa_sponsor"]
    assert order_table_columns(cols) == [
        "overall_fit",
        "job_title",
        "company",
        "job_url",
        "location_match",
        "visa_sponsor",
    ]


def test_order_table_columns_excludes_verbose_and_internal_fields():
    cols = ["overall_fit", "triage_summary", "technical_pros", "risk_factors", "red_flags", "where"]
    assert order_table_columns(cols) == ["overall_fit"]


def test_clean_list():
    # 1. Already a list
    assert clean_list(["a", "b"]) == ["a", "b"]

    # 2. String representation of a list (e.g. from dataframe serialization)
    assert clean_list("['a', 'b']") == ["a", "b"]

    # 3. Simple string
    assert clean_list("single item") == ["single item"]

    # 4. NaN or empty
    assert clean_list("NaN") == []
    assert clean_list("nan") == []
    assert clean_list("") == []
    assert clean_list(None) == []

    # 5. Invalid literal string representation fallback
    assert clean_list("[invalid list") == ["[invalid list"]
