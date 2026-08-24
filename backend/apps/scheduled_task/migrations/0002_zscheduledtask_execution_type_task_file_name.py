# Generated manually for execution_type / task_file_name

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scheduled_task', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='zscheduledtask',
            name='execution_type',
            field=models.CharField(
                db_index=True,
                default='file',
                max_length=32,
                verbose_name='执行类型',
            ),
        ),
        migrations.AddField(
            model_name='zscheduledtask',
            name='task_file_name',
            field=models.CharField(
                blank=True,
                default='',
                help_text='相对于 backend/task_file 目录下的文件名',
                max_length=256,
                verbose_name='执行文件名',
            ),
        ),
    ]
