from app.services.policy_knowledge import (
    COLLECTION_NAME,
    EMBEDDING_MODEL,
    index_policy_knowledge,
)


def main() -> None:
    count = index_policy_knowledge()

    print("FinSentinel policy indexing complete.")
    print("Collection:", COLLECTION_NAME)
    print("Embedding model:", EMBEDDING_MODEL)
    print("Policies indexed:", count)


if __name__ == "__main__":
    main()
