import os
import re
import json
from argparse import ArgumentParser
from enum import Enum
from glob import glob
from subprocess import DEVNULL, PIPE, Popen, run, SubprocessError
from typing import Dict, Generator, List, Optional, Set, Tuple

from iso639 import languages


class CodecType(Enum):
    Audio='audio'
    Video='video'
    Subtitle='subtitle'


class Language:
    def __init__(
        self: object,
        part1: str,
        part2t: str,
        part2b: str,
        name: str
    ):
        self._part1 = part1
        self._part2t = part2t
        self._part2b = part2b
        self._name = name

    @property
    def part1(self: object) -> str:
        return self._part1

    @property
    def part2t(self: object) -> str:
        return self._part2t

    @property
    def part2b(self: object) -> str:
        return self._part2b

    @property
    def name(self: object) -> str:
        return self._name

    def __str__(self: object):
        return self.name

    def __repr__(self: object):
        return f'<Language {str(self)}>'

    def __hash__(self: object) -> int:
        return hash(repr(self))

    def __eq__(self: object, other: object) -> bool:
        return type(self) is type(other) and hash(self) == hash(other)

    @staticmethod
    def from_string(string: str):
        for key in ['name', 'part1', 'part2t', 'part2b']:
            try:
                language = languages.get(**{key: string})
            except KeyError:
                continue
 
            return Language(
                language.part1,
                language.part2t,
                language.part2b,
                language.name
            )


DEFAULT_LANGUAGE = Language.from_string('eng')


class Stream:
    def __init__(
        self: object,
        index: int,
        codec_name: str,
        codec_type: CodecType,
        language: Optional[Language],
        attached_pic: bool
    ):
        self.index = index
        self.codec_name = codec_name
        self.codec_type = codec_type
        self.language = language
        self.attached_pic = attached_pic

    def is_valid_subtitle(self: object):
        return self.codec_type == CodecType.Subtitle and \
            self.codec_name in {'ass', 'dvd_subtitle', 'ssa', 'subrip'}

    def is_valid_stream(self: object):
        return self.codec_type in {CodecType.Audio, CodecType.Video} or \
            self.is_valid_subtitle()


def load_stream(stream_json: dict) -> Stream:
        stream_tags = stream_json.get('tags', {})
        stream_dispositions = stream_json.get('disposition', {})

        attached_pic = bool(stream_dispositions.get('attached_pic', False))
        language_string = stream_tags.get('language', None)

        return Stream(
            stream_json['index'],
            stream_json['codec_name'],
            CodecType(stream_json['codec_type']),
            language_string and Language.from_string(language_string),
            attached_pic
        )


class Movie:
    filename_pattern = re.compile(r'(?P<name>.+)\.(?P<type>.+)')

    def __init__(self: object, path: str):
        split = path.split('/')

        filename = split[-1]

        match = Movie.filename_pattern.match(filename)
        groupdict = match.groupdict()

        self.path = path
        self.name = groupdict['name']
        self.type = groupdict['type']
        self.directory = split[-2]

        self.streams = self.find_streams()
        self.subtitles = self.find_subtitles()

    def find_streams(self: object) -> List[Stream]:
        command = [
            'ffprobe',
            '-print_format', 'json',
            '-show_streams',
            self.path
        ]

        result = run(command, capture_output=True)
        result.check_returncode()

        result_output = json.loads(result.stdout)
        return list(map(load_stream, result_output['streams']))

    def find_subtitles(self: object) -> List[Stream]:
        return list(filter(lambda i: i.is_valid_subtitle(), self.streams))

    def output_path(self: object, output_dir: str) -> str:
        return f'{output_dir}/{self.directory}/{self.name} subtitles.mkv'


class ExternalSubtitle:
    def __init__(self: object, language: Optional[Language], name: str, path: str):
        self.language = language
        self.name = name
        self.path = path

    def __repr__(self: object) -> str:
        return f'<ExternalSubtitle "{self.name}" {self.language}>'

    @staticmethod
    def from_string(path: str):
        file_name = path.split('/')[-1]

        match = re.match(r'(?P<name>.+?)(\.(?P<language>[a-z]+?))?\.srt', file_name)
        groupdict = match.groupdict()

        return ExternalSubtitle(
            Language.from_string(groupdict['language']),
            groupdict['name'],
            path
        )


def get_language(language: Optional[Language]) -> str:
    if language is None:
        language = DEFAULT_LANGUAGE
    return language.part2b


class Analyser:
    def find_movies(
        self: object,
        movie_dir: str
    ) -> Generator[Movie, None, None]:
        for file_extension in ['mkv', 'mp4']:
            glob_string = f'{movie_dir}/**/*.{file_extension}' 
            for glob_result in glob(glob_string, recursive=True):
                if 'subtitles' in glob_result:
                    continue # todo: remove this once restarting the NAS
                yield Movie(glob_result)

    def find_external_subtitles(
        self: object,
        subtitle_dir: str
    ) -> Generator[ExternalSubtitle, None, None]:
        glob_string = f'{subtitle_dir}/**/*.srt'
        for glob_result in glob(glob_string, recursive=True):
            yield ExternalSubtitle.from_string(glob_result)

    def get_subtitle_path(self: object, movie_name: str, language: Language) -> Optional[str]:
        try:
            return self.subtitle_map[movie_name].get(language)
        except KeyError:
            return None

    def build_subtitle_map(self: object, subtitle_dir: str) -> None:
        self.subtitle_map = {}

        for subtitle in self.find_external_subtitles(subtitle_dir):
            if subtitle.name not in self.subtitle_map:
                self.subtitle_map[subtitle.name] = {}

            if subtitle.language:
                language = subtitle.language
            else:
                language = Language.from_string('en')

            self.subtitle_map[subtitle.name][language] = subtitle.path

    def __init__(
        self: object,
        movie_dir: str,
        output_dir: str,
        subtitle_dir: str
    ):
        self.build_subtitle_map(subtitle_dir)

        for movie in self.find_movies(movie_dir):
            output_path = movie.output_path(output_dir)

            if os.path.isfile(output_path):
                existing_movie = Movie(output_path)
                existing_languages = [i.language for i in existing_movie.subtitles]

                try:
                    missing_subtitles = [i for i in self.subtitle_map[movie.name] if i not in existing_languages]
                except KeyError:
                    missing_subtitles = []

                if missing_subtitles:
                    print(f'{movie.name} is missing {", ".join(i.name for i in missing_subtitles)}')
                    answer = input(f'Do you want to overwrite {output_path} with new languages? ')
                    if answer.lower() not in {'y', 'yes'}:
                        continue
                    os.remove(output_path)
                else:
                    print(f'Output file "{output_path}" already exists, skipping...')
                    continue

            existing_languages = [i.language for i in movie.subtitles]
            available_languages = list(self.subtitle_map.get(movie.name, []))

            missing_languages = [i for i in available_languages if i not in existing_languages]

            output_path_parent = '/'.join(output_path.split('/')[:-1])
            os.makedirs(output_path_parent, exist_ok=True)

            command = ['ffmpeg', '-i', 'pipe:0']
        
            for language in missing_languages:
                subtitle_path = self.get_subtitle_path(movie.name, language)
                command += ['-i', subtitle_path]

            video_streams = [i for i in movie.streams if \
                i.codec_type == CodecType.Video and not i.attached_pic]

            audio_streams = [i for i in movie.streams if \
                i.codec_type == CodecType.Audio]

            for index, stream in enumerate(video_streams):
                command += ['-map', f'0:{stream.index}']
                command += [f'-c:v:{index}', 'libx265']

            for stream in audio_streams:
                command += ['-map', f'0:{stream.index}']

            for index, stream in enumerate(movie.subtitles):
                language = get_language(stream.language)

                command += ['-map', f'0:{stream.index}']
                command += [f'-metadata:s:s:{index}', f'language={language}']
                command += [f'-c:s:{index}', stream.codec_name]

                if stream.language == DEFAULT_LANGUAGE:
                     command += [f'-disposition:s:{index}', 'default']
        
            for index, language  in enumerate(missing_languages):
                command += ['-map', f'{index + 1}:s']

                offset = len(movie.subtitles) + index

                command += [f'-metadata:s:s:{offset}', f'language={get_language(language)}']
                command += [f'-c:s:{offset}', 'subrip']

                if language == DEFAULT_LANGUAGE:
                     command += [f'-disposition:s:{offset}', 'default']

            attached_pics = [i for i in movie.streams if \
                i.codec_type == CodecType.Video and i.attached_pic]

            for index, stream in enumerate(attached_pics):
                command += ['-map', f'0:{stream.index}']

                offset = len(video_streams) + index

                command += [f'-c:v:{offset}', stream.codec_name]
                command += [f'-disposition:v:{offset}', 'attached_pic']

            # Commenting this out because we are using h265 encoding, for now.
            # # h264 needs even dimensions, No Country for Old Men does not have them.
            # # This rounds video dimensions up to the nearest even pixel number.
            # command += ['-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2']

            command += [output_path]

            print(f'Adding {", ".join(i.name for i in missing_languages)} subtitles to "{movie.name}"...')

            try:
                pv_command = Popen(['pv', movie.path], stdout=PIPE)
                result = run(command, encoding='utf-8', stderr=PIPE, stdin=pv_command.stdout)
                result.check_returncode()
            except (KeyboardInterrupt, SubprocessError) as error:
                print(f'Process was interrupted, deleting "{output_path}"...')
                try:
                    os.remove(output_path)
                except FileNotFoundError:
                    pass
                if isinstance(error, SubprocessError):
                    print(result.stderr)
                    raise error
                break



if __name__ == '__main__':
    analyser = Analyser(
        '/mnt/nfs/radarr',
        '/mnt/nfs/radarr_subtitles',
        '/mnt/nfs/bazarr'
    )
