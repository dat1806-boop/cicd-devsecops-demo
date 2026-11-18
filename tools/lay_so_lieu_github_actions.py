#!/usr/bin/env python3
"""Read-only GitHub Actions job-duration exporter. No runs are triggered."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
JOBS = ("test", "secret-scan", "sast", "sca", "build", "verify", "deploy-dev", "deploy-staging", "deploy-production")


def ts(value):
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def span(start, end):
    a,b=ts(start),ts(end)
    return round((b-a).total_seconds(), 2) if a and b and b>=a else ""


def github_get(url, token):
    headers = {"Accept": "application/vnd.github+json",
               "User-Agent": "WorkBoard-CICD-measurements", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req=urllib.request.Request(url,headers=headers)
    with urllib.request.urlopen(req,timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def summarize(run,jobs):
    chosen={}
    for j in jobs:
        if j.get("name") in JOBS and j.get("conclusion") in ("success", "failure"):
            chosen[j["name"]]=j
    row={"run_id":run.get("id"), "run_number":run.get("run_number"),
         "commit":run.get("head_sha","")[:12], "branch":run.get("head_branch",""),
         "url":run.get("html_url", ""),"conclusion":run.get("conclusion","")}
    for job in JOBS:
        j=chosen.get(job)
        row[job+"_s"]=span(j.get("started_at"),j.get("completed_at")) if j else ""
    ci=[chosen.get(j) for j in ("test","secret-scan","sast","sca")]
    ci=[j for j in ci if j and ts(j.get('started_at')) and ts(j.get('completed_at'))]
    if ci:
        row['ci_parallel_elapsed_s']=round((max(ts(j['completed_at']) for j in ci)-
                                             min(ts(j['started_at']) for j in ci)).total_seconds(),2)
    else:row['ci_parallel_elapsed_s']=''
    completed=[j for j in chosen.values() if ts(j.get('started_at')) and ts(j.get('completed_at'))]
    row['jobs_elapsed_s']=round((max(ts(j['completed_at']) for j in completed)-
                                 min(ts(j['started_at']) for j in completed)).total_seconds(),2) if completed else ''
    stag=chosen.get('deploy-staging');prod=chosen.get('deploy-production')
    row['staging_to_prod_gap_s']=(span(stag.get('completed_at'),prod.get('started_at'))
                                   if stag and prod else '')
    row['note']='Thời gian trước Production gồm scheduling/queue và phê duyệt, không tách được chỉ từ job timestamps.'
    return row


def main():
    ap=argparse.ArgumentParser(description='Lấy số liệu jobs của workflow GitHub Actions (chỉ đọc)')
    ap.add_argument('--repo',default='dat1806-boop/cicd-devsecops-demo')
    ap.add_argument('--branch',default='main',choices=('main','develop'))
    ap.add_argument('--count',type=int,default=3)
    args=ap.parse_args()
    if not __import__('re').fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',args.repo):
        ap.error('Repo phải theo dạng owner/name')
    if args.count<1 or args.count>10:
        ap.error('count phải trong khoảng 1..10')
    token=os.environ.get('GITHUB_TOKEN','')
    base='https://api.github.com/repos/'+args.repo+'/actions/'
    url=base+'workflows/pipeline.yml/runs?'+urllib.parse.urlencode(
        {'branch':args.branch,'status':'success','per_page':max(10,args.count*3)})
    try:
        runs=github_get(url,token).get('workflow_runs',[])[:args.count]
        if not runs:
            print('Không tìm thấy lượt chạy thành công tương ứng.');return 1
        records=[]
        for run in runs:
            jobs=[];page=1
            while True:
                data=github_get(base+f'runs/{run["id"]}/jobs?per_page=100&page={page}',token)
                jobs+=data.get('jobs',[])
                if len(data.get('jobs',[]))<100:break
                page+=1
            records.append(summarize(run,jobs))
    except (urllib.error.URLError,urllib.error.HTTPError,ValueError,KeyError) as exc:
        print('Không thể lấy số liệu GitHub:',exc)
        print('Kiểm tra mạng, quyền repository và GITHUB_TOKEN nếu repo riêng tư/rate limit.')
        return 2
    folder=PROJECT/'KET_QUA_DO_GITHUB';folder.mkdir(exist_ok=True)
    cols=['run_id','run_number','commit','branch','url','conclusion']+[j+'_s' for j in JOBS]+[
        'ci_parallel_elapsed_s','jobs_elapsed_s','staging_to_prod_gap_s','note']
    with (folder/'github_actions_jobs.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(records)
    (folder/'github_actions_jobs.json').write_text(json.dumps(records,indent=2,ensure_ascii=False),encoding='utf-8')
    print('Số lượt thành công:',len(records))
    for r in records:
        print(f'#{r["run_number"]} {r["commit"]} CI-parallel={r["ci_parallel_elapsed_s"]} s, total-jobs={r["jobs_elapsed_s"]} s')
    print('Đã lưu:',folder/'github_actions_jobs.csv')
    print('LƯU Ý: Tổng jobs_elapsed_s có thể bao gồm chờ phê duyệt và thời gian queue.')
    return 0


if __name__=='__main__':
    sys.exit(main())
