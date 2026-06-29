# LLMLingua Compression Service

FastAPI microservice for prompt compression using LLMLingua-2 (lossy) and lossless normalization.

## Building and Running Locally

### Build the Docker image:
```bash
docker build -t brevitas-compress:latest .
```

### Run the container:
```bash
# Without authentication
docker run -p 8080:8080 brevitas-compress:latest

# With Bearer token authentication
docker run -p 8080:8080 -e BREVITAS_COMPRESS_TOKEN=your-secret-token brevitas-compress:latest
```

## API Endpoints

### GET /health
Health check endpoint. Returns model status.

**Response:**
```json
{
  "status": "ok",
  "model_loaded": true
}
```

### POST /v1/optimize
Compress a prompt using LLMLingua-2 or lossless normalization.

**Request:**
```json
{
  "prompt": "Your prompt text here...",
  "rate": 0.5,
  "force_tokens": [".", "!", "?"]
}
```

**Parameters:**
- `prompt` (string, required): The prompt text to compress
- `rate` (float, default: 0.5): Target compression ratio
  - 1.0 = lossless normalization only (no lossy compression)
  - < 1.0 = enable lossy LLMLingua-2 compression (e.g., 0.5 keeps ~50% of tokens)
- `force_tokens` (array, optional): Tokens that LLMLingua-2 must preserve
  - Default: `["\n", ".", "!", "?", ",", ":"]`

**Response:**
```json
{
  "compressed_prompt": "Compressed text...",
  "tokens_before": 1250,
  "tokens_after": 625,
  "saved_pct": 50.0,
  "method": "llmlingua2+lossless",
  "lossy": true
}
```

**Response Fields:**
- `compressed_prompt`: The optimized prompt text
- `tokens_before`: Original token count (tiktoken cl100k_base)
- `tokens_after`: Compressed token count
- `saved_pct`: Percentage of tokens saved (0-100)
- `method`: Compression method used:
  - `"lossless"`: Whitespace normalization only
  - `"llmlingua2+lossless"`: Lossy LLMLingua-2 compression + lossless normalization
- `lossy`: Whether lossy compression was applied

## Authentication

If the environment variable `BREVITAS_COMPRESS_TOKEN` is set, all requests to `/v1/optimize` must include a Bearer token:

```bash
curl -X POST http://localhost:8080/v1/optimize \
  -H "Authorization: Bearer your-secret-token" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Your prompt...",
    "rate": 0.5
  }'
```

## Environment Variables

- `BREVITAS_COMPRESS_TOKEN` (optional): Bearer token for API authentication. If not set, the API is unauthenticated.

## Notes

### Model Warm-up
The first request after startup will trigger model loading and download (~1-2 seconds). The LLMLingua-2 model (bert-base-multilingual) is downloaded from Hugging Face on first use and cached locally.

### Image Size
The Docker image is approximately **3-4 GB** due to:
- Python 3.11 base image (~500 MB)
- PyTorch CPU (~2.5 GB)
- LLMLingua-2 model + dependencies (~500 MB)

This is expected for a CPU-based inference service. For production, consider using a GPU base image or running on a machine with sufficient disk space.

### Compression Behavior

**Lossless (rate >= 1.0):**
- Collapses excessive whitespace
- Removes blank lines beyond two consecutive newlines
- Trims trailing spaces (preserves code block indentation)
- **No semantic loss**

**Lossy (rate < 1.0):**
- Uses LLMLingua-2 (Microsoft, ACL'24) to identify low-importance tokens
- Trained as a token classifier on GPT-4 + human feedback
- Effective for 2-5x compression with strong semantic preservation
- **Verify outputs on critical prompts**

## API Contract

See `/v1/optimize` request/response schemas above for the complete contract.
