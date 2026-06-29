#!/bin/bash
set -e

echo "Starting Ollama server daemon..."
ollama serve &

echo "Waiting for Ollama service to bind on port 11434..."
until curl -s http://localhost:11434/ > /dev/null; do
    sleep 2
done

echo "Ollama is online. Enforcing required model layers..."
ollama pull qwen2.5:3b
ollama pull all-minilm

echo "Model sync verified successfully. Transitioning to active monitoring loop."
# Keep container active by waiting on the backgrounded engine process
wait -n