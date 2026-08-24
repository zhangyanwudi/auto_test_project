from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scheduled_task', '0002_zscheduledtask_execution_type_task_file_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='zscheduledtask',
            name='last_run_success',
            field=models.BooleanField(blank=True, null=True, verbose_name='最近执行是否成功'),
        ),
        migrations.AddField(
            model_name='zscheduledtask',
            name='last_run_message',
            field=models.CharField(blank=True, default='', max_length=512, verbose_name='最近执行说明'),
        ),
        migrations.AddField(
            model_name='zscheduledtask',
            name='last_run_detail',
            field=models.TextField(blank=True, default='', verbose_name='最近执行详情JSON'),
        ),
    ]
