import fnmatch
import math
import re
from dataclasses import dataclass, field
from urllib.parse import quote, urlsplit

from app.crawler.urls import CrawlError, percent_normalize

PRODUCT_TOKEN = "WebCrawlerStudio"
USER_AGENT = "WebCrawlerStudio/0.3 (educational crawler; respects robots.txt)"


@dataclass
class Rule:
    pattern: re.Pattern[str]
    length: int
    allow: bool


@dataclass
class Policy:
    rules: list[Rule] = field(default_factory=list)
    delay: float = 0
    denied: bool = False

    def allows(self, url: str) -> bool:
        if self.denied:
            return False
        parts = urlsplit(url)
        path = percent_normalize(
            quote(
                (parts.path or "/") + ("?" + parts.query if parts.query else ""),
                safe="/?&=:%*$@!()+,;~-._",
            )
        )
        matching = [rule for rule in self.rules if rule.pattern.match(path)]
        return not matching or max(matching, key=lambda rule: (rule.length, rule.allow)).allow


def parse_robots(text: str) -> Policy:
    groups: list[tuple[list[str], Policy]] = []
    agents: list[str] = []
    policy = Policy()
    directives = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        name, value = (item.strip() for item in line.split(":", 1))
        name = name.lower()
        if name == "user-agent":
            if not re.fullmatch(r"\*|[a-zA-Z0-9_-]{1,200}", value):
                raise CrawlError("robots_invalid", "Nieprawidłowy identyfikator robots.txt")
            if directives:
                groups.append((agents, policy))
                agents, policy, directives = [], Policy(), False
            agents.append(value.lower())
        elif agents:
            directives = True
            if name in {"allow", "disallow"} and value:
                if len(value) > 2048 or len(policy.rules) >= 10000:
                    raise CrawlError("robots_invalid", "Zbyt duże reguły robots.txt")
                encoded = percent_normalize(quote(value, safe="/?&=:%*$@!()+,;~-._"))
                anchored = encoded.endswith("$")
                pattern = encoded[:-1] if anchored else encoded + "*"
                # fnmatch translates interior stars to atomic groups, avoiding regex backtracking.
                escaped = "".join(
                    "[[]"
                    if char == "["
                    else "[]]"
                    if char == "]"
                    else "[?]"
                    if char == "?"
                    else char
                    for char in pattern
                )
                policy.rules.append(
                    Rule(
                        re.compile(fnmatch.translate(escaped)),
                        len(encoded.replace("*", "").rstrip("$")),
                        name == "allow",
                    )
                )
            elif name in {"crawl-delay", "request-rate"}:
                try:
                    if name == "crawl-delay":
                        delay = float(value)
                    else:
                        requests, seconds = (float(item) for item in value.split("/"))
                        if requests <= 0:
                            raise ValueError("request rate")
                        delay = seconds / requests
                    if not math.isfinite(delay) or delay < 0:
                        raise ValueError("delay")
                    policy.delay = max(policy.delay, delay)
                except (ValueError, ZeroDivisionError) as error:
                    raise CrawlError(
                        "robots_invalid", "Nieprawidłowe opóźnienie robots.txt"
                    ) from error
    if agents:
        groups.append((agents, policy))
    matches = []
    token = PRODUCT_TOKEN.lower()
    for names, group in groups:
        specificity = max(
            (len(agent) for agent in names if agent != "*" and agent in token), default=0
        )
        if specificity or "*" in names:
            matches.append((specificity, group))
    if not matches:
        return Policy()
    best = max(specificity for specificity, _ in matches)
    selected = [policy for specificity, policy in matches if specificity == best]
    return Policy(
        rules=[rule for policy in selected for rule in policy.rules],
        delay=max(policy.delay for policy in selected),
    )
