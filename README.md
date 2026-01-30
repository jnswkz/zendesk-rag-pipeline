# OptiBot Mini-Clone (OptiSigns Back-End Take-Home)

A small pipeline that:
1) pulls Help Center articles from `support.optisigns.com` (via Zendesk Help Center API),
2) normalizes each article to clean Markdown,
3) chunks the Markdown for retrieval,
4) uploads (delta-only) chunks to an OpenAI Vector Store via API,
5) runs once per day as a scheduled job on DigitalOcean.

---

## Running locally
- Build:
```
docker build -t bot .
```
- Run once and exit 0:
```
docker run --rm \
  -e OPENAI_API_KEY="sk-..." \
    bot
```

## Chunking strategy 
Support articles vary a lot (how-to steps, troubleshooting, long guides, code snippets). I chunk by semantic structure:
- Split by Markdown headings (#, ##, ###) to keep sections coherent.
- Target chunk size: ~400–800 tokens of text (configurable), with small overlap (optional).
- Metadata injection: Every chunk starts with:

    `Title: ...`

    `Article URL: ...`

    `Section: <heading path>`

    `Updated At: ...`

This makes retrieval more reliable and helps the assistant cite “Article URL:” lines even when only a portion of a section is retrieved.
Chunks are written as separate .md files under data/chunks/<article_id>/....


