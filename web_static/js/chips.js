function renderChipGroup(container, items, selected, onClick, extraClassMap, displayNames) {
  container.innerHTML = "";
  if (!items || !items.length) {
    container.innerHTML = '<span class="chip-none">none</span>';
    return;
  }
  items.forEach(function(name) {
    var chip = document.createElement("button");
    chip.className = "chip" + (name === selected ? " selected" : "");
    var extra = extraClassMap ? extraClassMap[name] : null;
    if (extra) chip.className += " " + extra;
    chip.textContent = displayNames && displayNames[name] ? displayNames[name] : name;
    chip.addEventListener("click", function() { onClick(name); });
    container.appendChild(chip);
  });
}
