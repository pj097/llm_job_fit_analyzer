podman run --rm -it --entrypoint python \
    -v ./demo:/app/demo:z \
    -v ./scripts:/app/scripts:z \
    -v ./data:/app/data:z \
    -v ./search_results:/app/search_results:z \
    --add-host host.containers.internal:host-gateway \
    --env OLLAMA_HOST=http://host.containers.internal:11434 \
    job-analyzer:latest scripts/record_demo.py