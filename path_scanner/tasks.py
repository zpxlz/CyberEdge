from django.utils import timezone
from celery import shared_task
import subprocess
import json
import uuid
from .models import PathScanJob, PathScanResult  # 确保导入模型

@shared_task(bind=True)
def scan_paths(self, wordlist, url):
    # 创建PathScanJob实例
    scan_job = PathScanJob.objects.create(target=url, status='R', task_id=self.request.id)

    # 构建输出文件名
    output_file_path = f"/tmp/{scan_job.task_id}.json"

    # 构建ffuf命令
    cmd = f"ffuf -w {wordlist} -u {url} -o {output_file_path} -of json"

    try:
        # 执行ffuf命令
        process = subprocess.run(cmd, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # 解析ffuf输出结果
        with open(output_file_path, 'r') as file:
            results = json.load(file)
            if 'results' in results:
                for result in results['results']:
                    PathScanResult.objects.create(
                        path_scan_job=scan_job,
                        url=url.replace('FUZZ', result['input']['FUZZ']),
                        content_type=result.get('content_type', ''),
                        status=result['status'],
                        length=result['length']
                    )
                scan_job.status = 'C'  # 标记为完成
            else:
                scan_job.status = 'E'
                scan_job.error_message = 'ffuf扫描没有返回结果'
    except subprocess.CalledProcessError as e:
        scan_job.status = 'E'  # 标记为错误
        scan_job.error_message = f'ffuf扫描失败: {e.stderr.decode()}'
    except Exception as e:
        scan_job.status = 'E'  # 标记为错误
        scan_job.error_message = f'处理ffuf扫描结果时发生异常: {str(e)}'
    finally:
        scan_job.end_time = timezone.now()
        scan_job.save()

        # 可选：删除输出文件或保留供后续审查

        if scan_job.status == 'E':
            return {'error': scan_job.error_message}
        return {'message': f'路径扫描完成: {url}'}