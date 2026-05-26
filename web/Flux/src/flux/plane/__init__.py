__all__ = ["sample_runtime_bad_quality", "seed_plane_samples_from_runtime_history"]


def __getattr__(name):
    if name == "sample_runtime_bad_quality":
        from .runtime import sample_runtime_bad_quality

        return sample_runtime_bad_quality
    if name == "seed_plane_samples_from_runtime_history":
        from .sample_seed import seed_plane_samples_from_runtime_history

        return seed_plane_samples_from_runtime_history
    raise AttributeError(name)
