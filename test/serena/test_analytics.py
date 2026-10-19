import pytest
import tiktoken

from serena.analytics import RegisteredTokenCountEstimator, TiktokenCountEstimator, ToolUsageStats


@pytest.fixture
def tiktoken_encoding(monkeypatch: pytest.MonkeyPatch) -> tiktoken.Encoding:
    encoding = tiktoken.Encoding(
        name="test_special_tokens",
        pat_str=r"(?s:.)",
        mergeable_ranks={bytes([value]): value for value in range(256)},
        special_tokens={"<|endoftext|>": 256, "<|endofprompt|>": 257},
    )
    monkeypatch.setattr(tiktoken, "encoding_for_model", lambda _: encoding)
    return encoding


@pytest.mark.parametrize(
    "text",
    [
        "",
        "ordinary source text",
        "<|endoftext|>",
        "<|endofprompt|>",
        "Documentation may show <|endoftext|> and <|endofprompt|> as literal text.",
    ],
)
def test_tiktoken_estimator_counts_special_token_literals_as_ordinary_text(tiktoken_encoding: tiktoken.Encoding, text: str) -> None:
    estimator = TiktokenCountEstimator()

    assert estimator.estimate_token_count(text) == len(tiktoken_encoding.encode_ordinary(text))


def test_tool_usage_stats_records_special_token_literals(monkeypatch: pytest.MonkeyPatch, tiktoken_encoding: tiktoken.Encoding) -> None:
    estimator = TiktokenCountEstimator()
    monkeypatch.setattr(RegisteredTokenCountEstimator, "load_estimator", lambda _: estimator)
    stats = ToolUsageStats(RegisteredTokenCountEstimator.TIKTOKEN_GPT4O)
    input_text = "Read <|endoftext|> literally"
    output_text = "Wrote <|endofprompt|> literally"

    stats.record_tool_usage("read_file", input_text, output_text)

    assert stats.get_stats("read_file") == ToolUsageStats.Entry(
        num_times_called=1,
        input_tokens=len(tiktoken_encoding.encode_ordinary(input_text)),
        output_tokens=len(tiktoken_encoding.encode_ordinary(output_text)),
    )
