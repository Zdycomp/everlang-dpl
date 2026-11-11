# Running Ever in the container

```bash
# build and verify every layer, including Ruby and Java
docker compose run --rm verify

# watch the self-generating loop
docker compose run --rm evolve

# the research team: conservation law, ratios, defect profile
docker compose run --rm research

# the live interpreter at http://localhost:8088/ever-live.html
docker compose up live

# a shell inside the image
docker compose run --rm shell
```

The image verifies itself at build time. If any layer fails, the build
fails — an image that ships without its own tests passing ships a claim
instead of a result.
