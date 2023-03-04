format:
	monoformat .

check_release:
ifndef VERSION
	$(error VERSION is undefined)
endif

release: check_release
	git flow release start $(VERSION)
	sed -i 's/^version =.*/version = "$(VERSION)"/' api/pyproject.toml
	sed -i 's/^version =.*/version = "$(VERSION)"/' package/pyproject.toml
	sed -i 's/^"version"\s*:.*/"version": "$(VERSION)",/' npym-info/package.json
	git add api/pyproject.toml package/pyproject.toml
	git commit -m "Bump version to $(VERSION)"
	git flow release finish -m "Release $(VERSION)" $(VERSION) > /dev/null
