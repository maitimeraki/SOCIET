import asyncio
from src.graph.models_graph import GraphInputDocument
from src.graph.graph_pipeline import UniversalGraphPipeline


async def main():
    docs = [
        GraphInputDocument(document_id="d1", title="Manual", text="System A depends on Module B."),
        GraphInputDocument(document_id="d2", title="Legal", text="Company X signed an agreement with Company Y."),
    ]

    pipeline = UniversalGraphPipeline()
    result = await pipeline.run(dataset_id="batch_001", documents=docs)
    print(result)


def run_main():
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(main())
        return None

    return loop.create_task(main())


if __name__ == "__main__":
    run_main()
