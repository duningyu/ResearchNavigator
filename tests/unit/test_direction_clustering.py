from research_navigator.clustering.service import cluster_documents


def test_clustering_is_deterministic_and_threshold_sensitive() -> None:
    documents = {
        3: "transformer attention forecasting time series",
        1: "temporal convolution anomaly detection time series",
        2: "convolutional network anomaly detection industrial time series",
        4: "language model retrieval augmented generation documents",
    }
    first = cluster_documents(documents, threshold=0.25)
    second = cluster_documents(dict(reversed(list(documents.items()))), threshold=0.25)
    assert first == second
    assert first[1]["component"] == first[2]["component"]
    assert first[4]["unclustered"] is True

    strict = cluster_documents(documents, threshold=0.95)
    assert all(item["unclustered"] is True for item in strict.values())
