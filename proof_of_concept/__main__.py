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
        self.part1 = part1
        self.part2t = part2t
        self.part2b = part2b
        self.name = name

    def __str__(self: object):
        return self.name

    def __repr__(self: object):
        return f'<Language {str(self)}>'

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


def load_stream(stream_json: dict) -> List[Stream]:
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


# BAZARR_PATH='/mnt/nfs/pi.croydon.vpn/bazarr'
# 
# CODEC_CHAR_MAP = {
#     CodecType.Audio: 'a',
#     CodecType.Video: 'v',
#     CodecType.Subtitle: 's'
# }
# 
# 
# 
# 
# def get_stream_list(path: str) -> List[Stream]:
#     command = [
#         'ffprobe',
#         '-print_format', 'json',
#         '-show_streams',
#         path
#     ]
# 
#     result = subprocess.run(command, capture_output=True)
#     result.check_returncode()
# 
#     return list(map(load_stream, json.loads(result.stdout)['streams']))
# 
# 
# def is_valid_subtitle(stream: Stream):
#     return stream.codec_type == CodecType.Subtitle and \
#         stream.codec_name in {'dvd_subtitle', 'subrip'}
#     
# 
# def is_valid_stream(stream: Stream):
#     if stream.codec_type in {CodecType.Audio, CodecType.Video}:
#         return True
#     return is_valid_subtitle(stream)
# 
# 
# def missing_subtitles(stream_list: List[Stream]) -> List[Language]:
#     valid_subtitles = list(filter(is_valid_subtitle, stream_list))
# 
#     subtitle_status = {i: False for i in Language}
# 
#     for subtitle in valid_subtitles:
#         for language in Language:
#             if subtitle.language in COUNTRY_CODES[language]:
#                 subtitle_status[language] = True
#                 break
# 
#     return [i for i in Language if not subtitle_status[i]]
# 
# 
# def find_subtitle_file(name: str, language: Language) -> Optional[str]:
#     for country_code in COUNTRY_CODES[language]:
#         file_name = f'{BAZARR_PATH}/{name}.{country_code}.srt'
#         if os.path.isfile(file_name):
#             return file_name
# 
# 
# def find_subtitles(name: str, languages: List[Language]) -> List[Tuple[Language, str]]:
#     result = []
# 
#     for language in languages:
#         file_name = find_subtitle_file(name, language)
# 
#         if not file_name:
#             continue
# 
#         result += [(language, file_name)]
# 
#     return result
# 
# 
# def analyse_movie(path: str) -> None:
#     stream_list = get_stream_list(path)
# 
#     valid_streams = list(filter(is_valid_stream, stream_list))
#     valid_subtitles = list(filter(is_valid_subtitle, stream_list))
# 
#     required_subtitles = missing_subtitles(stream_list)
#     found_subtitles = find_subtitles(Movie(path).name, required_subtitles)
# 
#     command = ['ffmpeg', '-i', path]
# 
#     for subtitle in found_subtitles:
#         command += ['-i', subtitle[1]]
# 
#     for stream in valid_streams:
#         command += ['-map', f'0:{stream.index}']
# 
#     for index in range(len(found_subtitles)):
#         command += ['-map', f'{index + 1}:s']
# 
#     for item in enumerate(map(lambda i: i[0], found_subtitles)):
#         offset, language = item
#         index = len(valid_subtitles) + offset
#         cc_string = COUNTRY_CODES[language][-1]
#         command += [f'-metadata:s:s:{index}', f'language={cc_string}']
# 
#     command += ['-scodec', 'copy']
#     command += ['output.mkv']
# 
#     result = subprocess.run(command)
#     result.check_returncode()


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
        wanted_languages: List[Language],
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
            print(f'Movie name: {movie.name}')
            missing_subtitles = movie.missing_subtitles(wanted_languages)
            print(f'Missing subtiles: {list(map(lambda i: i.part1, missing_subtitles))}')
            available_subtitles = [i for i in missing_subtitles if self.get_subtitle_path(movie.name, i)]
            print(f'Available subtiles: {list(map(lambda i: i.part1, available_subtitles))}')

            if not missing_subtitles or not available_subtitles:
                continue

            output_filename = f'{movie_dir}/{movie.name}/{movie.name} subtitles.mkv'

            command = ['ffmpeg', '-i', movie.path]
        
            for subtitle in available_subtitles:
                subtitle_path = self.get_subtitle_path(movie.name, subtitle)
                command += ['-i', subtitle_path]
        
            for stream in filter(lambda i: i.is_valid_stream(), movie.streams):
                command += ['-map', f'0:{stream.index}']
        
            for index in range(len(available_subtitles)):
                command += ['-map', f'{index + 1}:s']
        
            for index, language in enumerate(available_subtitles):
                offset = len(movie.subtitles) + index
                command += [f'-metadata:s:s:{offset}', f'language={language.part2b}']
        
            command += ['-scodec', 'copy']
            command += ['test.mkv']
        
            result = subprocess.run(command)
            result.check_returncode()

            exit(1)



if __name__ == '__main__':
    analyser = Analyser(
        list(map(Language.from_string, ['en', 'sl', 'ko', 'ja', 'zh'])),
        '/mnt/nfs/pi.croydon.vpn/radarr',
        '/mnt/nfs/pi.croydon.vpn/bazarr'
    )
