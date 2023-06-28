from argparse import ArgumentParser
from itertools import chain
from json import dump, load
from functools import partial
from multiprocessing import Pool
from os import replace
from os.path import exists, join
from pathlib import Path
from subprocess import DEVNULL, check_call
from typing import Optional, Tuple
from re import sub
from unicodedata import normalize

from requests import get

# from doc2json.grobid2json.process_pdf import process_pdf_file

with open("headers.json") as f:
    headers = load(f)
paper_fields = "paperId,externalIds,title,venue,openAccessPdf,fieldsOfStudy,authors"
author_fields = f"authorId,name,aliases,affiliations,hompage,paperCount,citationCount,hIndex,papers,{','.join(f'papers.{field}' for field in paper_fields.split(','))}"
citation_reference_fields = f"contexts,intents,{paper_fields}"
search_url = "https://api.semanticscholar.org/graph/v1/paper/search"
with open("seed_titles.json") as f:
    seed_titles = load(f)
# 将搜出的且有pdf下载链接的论文的链接和externalIds做匹配，得到url_patterns，便于后续利用url_patterns和externalIds下载
if exists("url_patterns.json"):
    with open("url_patterns.json", "r") as f:
        url_patterns = load(f)
else:
    url_patterns = {}

def search_func(seed_title: str):
    params = {"query": seed_title, "fields": paper_fields}
    response = get(search_url, params=params, headers=headers)
    if response.status_code == 200:
        seed_title = sub("[^a-z0-9]+", "_", normalize("NFKC", seed_title).lower())
        for paper in response.json()["data"]:
            if sub("[^a-z0-9]+", "_", normalize("NFKC", paper["title"]).lower()) == seed_title:
                if "openAccessPdf" in paper and type(paper["openAccessPdf"]) is dict and "url" in paper["openAccessPdf"] and type(paper["openAccessPdf"]["url"]) is str:
                    for key, externalId in paper["externalIds"].items():
                        if key == "DOI":
                            continue
                        if len(splited := paper["openAccessPdf"]["url"].split(str(externalId))) == 2:
                            url_patterns[key] = splited
                            break
                paper = citations_func(paper)
                paper = references_func(paper)
                return paper
    return None

def citations_func(paper: dict, paper_key: Optional[str] = None, all_papers: Optional[dict]=None):
    if "citations" not in paper:
        url = f"https://api.semanticscholar.org/graph/v1/paper/{paper['paperId']}/citations"
        params = {"fields": citation_reference_fields}
        response = get(url, params=params, headers=headers)
        if response.status_code == 200:
            paper["citations"] = response.json()["data"]
        else:
            paper["citations"] = []
    if all_papers is not None:
        paper["citations"] = [citation for citation in paper["citations"] if sub("[^a-z0-9]+", "_", normalize("NFKC", citation["citingPaper"]["title"]).lower()) in all_papers]
    if paper_key is None:
        return paper
    return paper_key, paper

def references_func(paper: dict, paper_key: Optional[str] = None, all_papers: Optional[dict]=None):
    if "references" not in paper:
        url = f"https://api.semanticscholar.org/graph/v1/paper/{paper['paperId']}/references"
        params = {"fields": citation_reference_fields}
        response = get(url, params=params, headers=headers)
        if response.status_code == 200:
            paper["references"] = response.json()["data"]
        else:
            paper["references"] = []
    if all_papers is not None:
        paper["references"] = [reference for reference in paper["references"] if sub("[^a-z0-9]+", "_", normalize("NFKC", reference["citedPaper"]["title"]).lower()) in all_papers]
    if paper_key is None:
        return paper
    return paper_key, paper

def author_papers_func(authorId: str):
    url = f"https://api.semanticscholar.org/graph/v1/author/{authorId}/papers"
    params = {"fields": paper_fields}
    response = get(url, params=params, headers=headers)
    if response.status_code == 200:
        return response.json()["data"]
    return []

def download_func(paper_item: Tuple[str, dict], download_path: str, temp_path: str, output_path: str, proxy: bool = False):
    paper_key, paper = paper_item
    pdf_path = join(download_path, f"{paper_key}.pdf")
    urls = []
    if "openAccessPdf" in paper and type(paper["openAccessPdf"]) is dict and "url" in paper["openAccessPdf"] and type(paper["openAccessPdf"]["url"]) is str:
        urls.append(("", paper["openAccessPdf"]["url"]))
    if "externalIds" in paper and paper["externalIds"] is not None:
        urls.extend((f"_{key}", f"{url_patterns[key][0]}{externalId}{url_patterns[key][1]}") for key, externalId in paper["externalIds"].items() if key in url_patterns)
    for key, url in urls:
        try:
            print(f"downloading {url}")
            if proxy:
                try:
                    check_call(["wget", "-c", "-U", "NoSuchBrowser/1.0", "-t", "1", url, "-O", f"{pdf_path}{key}"], stdout=DEVNULL, stderr=DEVNULL)
                except:
                    # 代理需要tsocks
                    check_call(["tsocks", "wget", "-c", "-U", "NoSuchBrowser/1.0", "-t", "1", url, "-O", f"{pdf_path}{key}"], stdout=DEVNULL, stderr=DEVNULL)
            else:
                # NoSuchBrowser/1.0用来修复arxiv下载403问题，-c断点续传，key用于区分不同来源的pdf，禁止重试
                check_call(["wget", "-c", "-U", "NoSuchBrowser/1.0", "-t", "1", url, "-O", f"{pdf_path}{key}"], stdout=DEVNULL, stderr=DEVNULL)
            print(f"downloaded {url}")
            # process_pdf_file(pdf_path, temp_path, output_path)
            replace(f"{pdf_path}{key}", pdf_path)
            print("crawled", paper_key)
            return None
        except Exception as e:
            pass
    return paper_key


def main(args):
    pool = Pool(args.num_workers)
    if args.redo or not exists("all_papers.json"):
        papers = [d for d in pool.map(search_func, seed_titles) if d is not None]

        # 存在重复的论文，所以用标题作为键
        all_papers = {}

        for paper in papers:
            # 种子论文
            all_papers[sub("[^a-z0-9]+", "_", normalize("NFKC", paper["title"]).lower())] = paper
            # 种子论文citations的论文
            for citation in paper["citations"]:
                if (paper_key := sub("[^a-z0-9]+", "_", normalize("NFKC", citation["citingPaper"]["title"]).lower())) not in all_papers:
                    if "openAccessPdf" in citation["citingPaper"] and type(citation["citingPaper"]["openAccessPdf"]) is dict and "url" in citation["citingPaper"]["openAccessPdf"] and type(citation["citingPaper"]["openAccessPdf"]["url"]) is str:
                        for key, externalId in citation["citingPaper"]["externalIds"].items():
                            if key == "DOI":
                                continue
                            if key not in url_patterns and len(splited := citation["citingPaper"]["openAccessPdf"]["url"].split(str(externalId))) == 2:
                                url_patterns[key] = splited
                                break
                    all_papers[paper_key] = citation["citingPaper"]
            # 种子论文references的论文
            for reference in paper["references"]:
                if (paper_key := sub("[^a-z0-9]+", "_", normalize("NFKC", reference["citedPaper"]["title"]).lower())) not in all_papers:
                    if "openAccessPdf" in reference["citedPaper"] and type(reference["citedPaper"]["openAccessPdf"]) is dict and "url" in reference["citedPaper"]["openAccessPdf"] and type(reference["citedPaper"]["openAccessPdf"]["url"]) is str:
                        for key, externalId in reference["citedPaper"]["externalIds"].items():
                            if key == "DOI":
                                continue
                            if key not in url_patterns and len(splited := reference["citedPaper"]["openAccessPdf"]["url"].split(str(externalId))) == 2:
                                url_patterns[key] = splited
                                break
                    all_papers[paper_key] = reference["citedPaper"]

        if args.authors:
            authorIds = [author["authorId"] for paper in papers for author in paper["authors"]]
            # 种子论文authors的论文
            for paper in chain(*pool.map(author_papers_func, authorIds)):
                if (paper_key := sub("[^a-z0-9]+", "_", normalize("NFKC", paper["title"]).lower())) not in all_papers:
                    if "openAccessPdf" in paper and type(paper["openAccessPdf"]) is dict and "url" in paper["openAccessPdf"] and type(paper["openAccessPdf"]["url"]) is str:
                        for key, externalId in paper["externalIds"].items():
                            if key == "DOI":
                                continue
                            if key not in url_patterns and len(splited := paper["openAccessPdf"]["url"].split(str(externalId))) == 2:
                                url_patterns[key] = splited
                                break
                    all_papers[paper_key] = paper

        with open("all_papers.json", "w") as f:
            dump(all_papers, f, indent=4)

    with open("all_papers.json") as f:
        all_papers = load(f)

    print("len(all_papers)", len(all_papers))

    download_path = Path("download")
    download_path.mkdir(exist_ok=True)
    temp_path = None
    output_path = None
    # temp_path = Path("s2orc_temp")
    # temp_path.mkdir(exist_ok=True)
    # output_path = Path("s2orc_output")
    # output_path.mkdir(exist_ok=True)

    if args.download:
        papers_to_download = all_papers.items()
        if args.crawled is not None:
            with open(args.crawled) as f:
                crawled = set(l.rstrip("\n") for l in f)
            papers_to_download = [(paper_key, paper) for paper_key, paper in papers_to_download if paper_key not in crawled]
            print(f"{len(crawled)} papers already crawled")
        print("len(papers_to_download)", len(papers_to_download))
        with open("url_patterns.json", "w") as f:
            dump(url_patterns, f, indent=4)
        # 部分论文下载失败，删除
        keys_to_remove = pool.map(partial(download_func, download_path=download_path, temp_path=temp_path, output_path=output_path, proxy=args.proxy), papers_to_download)
        for key in keys_to_remove:
            if key in all_papers:
                del all_papers[key]
        print("len(all_papers) after download", len(all_papers))

    all_papers = dict(pool.starmap(partial(citations_func, all_papers=all_papers), [(paper, paper_key) for paper_key, paper in all_papers.items()]))
    all_papers = dict(pool.starmap(partial(references_func, all_papers=all_papers), [(paper, paper_key) for paper_key, paper in all_papers.items()]))

    with open("all_papers.json", "w") as f:
        dump(all_papers, f, indent=4)

    # 用authorId作为键
    all_authors = {}
    # all_papers的全部作者
    for paper in all_papers.values():
        for author in paper["authors"]:
            all_authors[author["authorId"]] = author
    print("len(all_authors)", len(all_authors))

    with open("all_authors.json", "w") as f:
        dump(all_authors, f, indent=4)

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--authors", "-a", action="store_true")
    parser.add_argument("--crawled", "-c", type=str)
    parser.add_argument("--download", "-d", action="store_true")
    parser.add_argument("--num_workers", "-nw", type=int, default=16)
    parser.add_argument("--proxy", "-p", action="store_true")
    parser.add_argument("--redo", "-r", action="store_true")
    args = parser.parse_args()

    main(args)
