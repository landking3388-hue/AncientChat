from langchain.embeddings import OpenAIEmbeddings

class ModelScopeEmbedding:
    def __init__(self):
        self._embedding = OpenAIEmbeddings()

    @property
    def embedding(self):
        return self._embedding