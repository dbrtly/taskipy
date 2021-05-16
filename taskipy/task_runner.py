import sys
import platform
import psutil  # type: ignore
import signal
import subprocess
import shlex
import mslex # type: ignore
from pathlib import Path
from typing import List, Union, Optional

from taskipy.pyproject import PyProject
from taskipy.exceptions import TaskNotFoundError
from taskipy.task import Task
from taskipy.help import HelpFormatter


class TaskRunner:
    def __init__(self, cwd: Union[str, Path]):
        working_dir = cwd if isinstance(cwd, Path) else Path(cwd)
        self.__working_dir = working_dir
        self.__project = PyProject(working_dir)

    def list(self):
        """lists tasks to stdout"""
        formatter = HelpFormatter(self.__project.tasks.values())
        formatter.print()

    def run(self, task_name: str, args: List[str]) -> int:
        try:
            task = self.__project.tasks[task_name]
        except KeyError:
            raise TaskNotFoundError(task_name)

        pre_task = self.__pre_task(task_name)
        if pre_task is not None:
            exit_code = self.__run_command_and_return_exit_code(pre_task.command)
            if exit_code != 0:
                return exit_code

        exit_code = self.__run_command_and_return_exit_code(task.command, args)
        if exit_code != 0:
            return exit_code

        post_task = self.__post_task(task_name)
        if post_task is not None:
            exit_code = self.__run_command_and_return_exit_code(post_task.command)
            if exit_code != 0:
                return exit_code

        return 0

    def __run_command_and_return_exit_code(self, command: str, args: List[str] = None) -> int:
        if args is None:
            args = []

        if self.__project.runner is not None:
            command = f'{self.__project.runner} {command}'

        def quote_arg(arg: str) -> str:
            if platform.system() == 'Windows':
                return mslex.quote(arg)
            return shlex.quote(arg)

        def send_signal_to_task_process(signum: int, _frame) -> None:
            # pylint: disable=W0640
            psutil_process_wrapper = psutil.Process(process.pid)
            is_direct_subprocess_a_shell_process = sys.platform != 'darwin'  # pylint: disable=C0103

            if is_direct_subprocess_a_shell_process:
                # A shell is created because of Popen(..., shell=True) on linux only
                # We want here to kill shell's child
                sub_processes_of_taskipy_shell = psutil_process_wrapper.children()
                for child_process in sub_processes_of_taskipy_shell:
                    child_process.send_signal(signum)
            else:
                process.send_signal(signum)

        command_with_args = ' '.join([command] + [quote_arg(arg) for arg in args])
        process = subprocess.Popen(command_with_args,
                                   shell=True,
                                   cwd=self.__working_dir)
        signal.signal(signal.SIGTERM, send_signal_to_task_process)

        try:
            process.wait()
        except KeyboardInterrupt:
            pass

        return process.returncode

    def __pre_task(self, task_name: str):
        return self.__find_hooks('pre', task_name)

    def __post_task(self, task_name: str):
        return self.__find_hooks('post', task_name)

    def __find_hooks(self, hook_type: str, task_name: str) -> Optional[Task]:
        try:
            return self.__project.tasks[f'{hook_type}_{task_name}']
        except KeyError:
            return None
