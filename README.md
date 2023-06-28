# paper_retriever

## Get started

Get a semantic scholar API key from [here](https://www.semanticscholar.org/product/api).

Create a file named `headers.json` in the root directory to store the API key. The file should have the following format:

```json
{"x-api-key": "api_key_here"}
```

Create a file named `seed_titles.json` in the root directory to store the seed titles. The file should have the following format:

```json
[
    "Automatic Detection of Repeated Objects in Images",
    "Fast Affine Invariant Image Matching", 
    "Distinctive Image Features from Scale-Invariant Keypoints",
    "gSpan: Graph-Based Substructure Pattern Mining",
    "An Open-Domain Cause-Effect Relation-Detection from Paired Nominals",
    "SkipBERT: Efficient Inference with Shallow Layer Skipping",
    "An image is worth 16x16 words: Transformers for image recognition at scale",
    "Attention bottlenecks for multimodal fusion",
    "What makes multi-modal learning better than single (provably)",
    "Learning one representation to optimize all rewards",
    "Towards lower bounds on the depth of ReLU neural networks",
    "A Frustratingly Easy Approach for Entity and Relation Extraction",
    "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding"
]
```

Run the following command to retrieve the papers:

```bash
python main.py
```
