// Matches Python's string.punctuation used by the server's password validator.
export const passwordPunctuation = "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"

export function hasPasswordPunctuation(value: string): boolean {
  return Array.from(value).some(character => passwordPunctuation.includes(character))
}

export function hasRequiredPasswordComposition(value: string): boolean {
  return value.length >= 9
    && /[A-Z]/.test(value)
    && /[a-z]/.test(value)
    && hasPasswordPunctuation(value)
}
