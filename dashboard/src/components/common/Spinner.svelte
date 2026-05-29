<div class="spinner" aria-label="Loading"></div>

<style>
  .spinner {
    width: 16px;
    height: 16px;
    border: 2px solid var(--border-strong);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
    display: inline-block;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
</style>
