import os
import re
import json
import subprocess
from argparse import ArgumentParser
from collections import defaultdict
from enum import Enum
from glob import glob
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
        for key in ['part1', 'part2t', 'part2b']:
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


class Stream:
    def __init__(
        self: object,
        index: int,
        codec_name: str,
        codec_type: CodecType,
        language: Optional[Language]
    ):
        self.index = index
        self.codec_name = codec_name
        self.codec_type = codec_type
        self.language = language

    def is_valid_subtitle(self: object):
        return self.codec_type == CodecType.Subtitle and \
            self.codec_name in {'ass', 'dvd_subtitle', 'ssa', 'subrip'}

    def is_valid_stream(self: object):
        return self.codec_type in {CodecType.Audio, CodecType.Video} or \
            self.is_valid_subtitle()


def load_stream(stream_json: dict) -> Stream:
        stream_tags = stream_json.get('tags')

        if stream_tags:
            language_string = stream_tags.get('language')
        else:
            language_string = None

        return Stream(
            stream_json['index'],
            stream_json['codec_name'],
            CodecType(stream_json['codec_type']),
            language_string and Language.from_string(language_string)
        )


class Movie:
    def __init__(self: object, path: str):
        file_name = path.split('/')[-1]
        match = re.match(r'(?P<name>.+)\.(?P<type>.+)', file_name)
        groupdict = match.groupdict()

        self.path = path
        self.name = groupdict['name']
        self.type = groupdict['type']

        self.streams = self.find_streams()
        self.subtitles = self.find_subtitles()

    def find_streams(self: object) -> List[Stream]:
        command = [
            'ffprobe',
            '-print_format', 'json',
            '-show_streams',
            self.path
        ]

        result = subprocess.run(command, capture_output=True)
        result.check_returncode()

        result_output = json.loads(result.stdout)
        return list(map(load_stream, result_output['streams']))

    def find_subtitles(self: object) -> List[Stream]:
        return list(filter(lambda i: i.is_valid_subtitle(), self.streams))

    def missing_subtitles(
        self: object,
        wanted_languages: List[Language]
    ) -> Set[Language]:
        existing_languages = set(i.language for i in self.subtitles)
        return set(i for i in wanted_languages if i not in existing_languages)


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


class Analyser:
    def find_movies(
        self: object,
        movie_dir: str
    ) -> Generator[Movie, None, None]:
        for file_extension in ['mkv', 'mp4']:
            glob_string = f'{movie_dir}/**/*.{file_extension}' 
            for glob_result in glob(glob_string):
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
            return self.subtitle_map[movie_name][language.part1]
        except KeyError:
            return None

    def __init__(
        self: object,
        movie_dir: str,
        subtitle_dir: str
    ):
        self.wanted_languages = wanted_languages
        self.subtitle_map = {}

        for subtitle in self.find_external_subtitles(subtitle_dir):
            if subtitle.name not in self.subtitle_map:
                self.subtitle_map[subtitle.name] = {}

            if subtitle.language:
                language = subtitle.language.part1
            else:
                language = 'en'

            self.subtitle_map[subtitle.name][language] = subtitle.path

        for movie in self.find_movies(movie_dir):
            available_languages = list(map(Language.from_string,
                self.subtitle_map.get(movie.name, [])))

            existing_languages = set(
                [i.language for i in movie.find_subtitles()])

            missing_languages = list(filter(
                lambda i: i not in existing_languages, available_languages))

            if not missing_languages:
                continue

            output_directory = '/'.join(movie.path.split('/')[0:-1])
            output_path = f'{output_directory}/{movie.name} subtitles.mkv'

            command = ['ffmpeg', '-i', movie.path]
        
            for language in missing_languages:
                subtitle_path = self.get_subtitle_path(movie.name, language)
                command += ['-i', subtitle_path]
        
            for stream in filter(lambda i: i.is_valid_stream(), movie.streams):
                command += ['-map', f'0:{stream.index}']
        
            for index , _value in enumerate(missing_languages):
                command += ['-map', f'{index + 1}:s']
        
            for index, language in enumerate(missing_languages):
                offset = len(movie.subtitles) + index
                command += [f'-metadata:s:s:{offset}', f'language={language.part2b}']
        
            command += ['-scodec', 'copy']
            command += [output_path]
            print(command)
            continue
        
            result = subprocess.run(command)
            result.check_returncode()


if __name__ == '__main__':
    analyser = Analyser(
        '/mnt/nas/pi.croydon.vpn/radarr',
        '/mnt/nas/pi.croydon.vpn/bazarr'
    )
